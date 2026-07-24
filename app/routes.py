"""
Flask Routes - Main and API blueprints

Two Flask blueprints are defined here:
  - main_bp : serves the HTML frontend (registered at '/')
  - api_bp  : provides the JSON REST API (registered at '/api/')

Request flow for a typical embed operation:
  1. POST /api/upload    -> save video, return file_id + video metadata
  2. POST /api/capacity  -> calculate how many bytes can be hidden
  3. POST /api/embed     -> start async (Celery) or synchronous embed task
  4. GET  /api/task/<id> -> poll Celery task status / progress
  5. GET  /api/download/<id> -> download the processed stego video
"""

import os
import uuid
from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

# Blueprints let us split routes into logical groups.
# main_bp handles the HTML page; api_bp handles JSON endpoints.
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)


def allowed_file(filename):
    """Check if uploaded file has allowed extension.

    Only video containers in ALLOWED_EXTENSIONS are accepted.
    The check uses rsplit to handle edge-cases like filenames with
    multiple dots (e.g. 'my.video.backup.mp4').
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def ensure_directories():
    """Ensure upload and output directories exist.

    Called at the start of routes that read/write files so the
    directories are created lazily rather than requiring them to
    exist before the server starts.
    """
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(current_app.config['OUTPUT_FOLDER'], exist_ok=True)


# ============= Main Routes =============

@main_bp.route('/')
def index():
    """Render the main application page.

    Returns the single-page HTML interface (templates/index.html).
    All user interaction happens through this page via AJAX and WebSockets.
    """
    return render_template('index.html')


@main_bp.route('/health')
def health():
    """Health check endpoint.

    Used by load balancers and monitoring tools to verify the service
    is running. Returns HTTP 200 with a JSON status payload.
    """
    return jsonify({'status': 'healthy', 'version': '2.0.0'})


@main_bp.route('/metrics')
def metrics():
    """Prometheus scrape endpoint.

    Registered on main_bp (not api_bp) so it lands at the root '/metrics'
    path Fly's managed Prometheus scraper (see the [[metrics]] block in
    fly.toml) and most external Prometheus configs expect by default,
    rather than under '/api/metrics'.
    """
    from app.metrics import render_metrics
    body, content_type = render_metrics()
    return body, 200, {'Content-Type': content_type}


# ============= API Routes =============

@api_bp.route('/upload', methods=['POST'])
def upload_video():
    """Upload a video file for processing.

    Accepts a multipart/form-data POST with a 'video' file field.
    The file is saved under a UUID-based name to avoid collisions and
    to prevent path traversal attacks from malicious filenames.

    Returns: file_id (used in subsequent API calls), original filename,
             and basic video metadata (resolution, FPS, frame count, capacity).
    """
    ensure_directories()

    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, avi, mov, mkv, webm'}), 400

    # Generate a UUID-based filename to:
    #   1. Avoid collisions when multiple users upload files concurrently
    #   2. Prevent directory traversal via crafted filenames
    file_id = str(uuid.uuid4())
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{file_id}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

    file.save(filepath)

    # Extract video metadata immediately after upload so the client
    # can display resolution, duration, and available embedding capacity.
    from app.services.video_service import VideoService
    video_info = VideoService.get_video_info(filepath)

    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': secure_filename(file.filename),
        'video_info': video_info
    })


@api_bp.route('/capacity', methods=['POST'])
def calculate_capacity():
    """Calculate embedding capacity for a video.

    Accepts a JSON body with 'file_id' and an optional list of 'frames'.
    When frames are specified, capacity is calculated only for those frames;
    otherwise the total capacity across all frames is returned.

    Capacity accounts for Reed-Solomon overhead (~10%) and AES
    encryption overhead (salt + IV + tag = 48 bytes).
    """
    data = request.get_json()

    if not data or 'file_id' not in data:
        return jsonify({'error': 'file_id is required'}), 400

    file_id = data['file_id']
    frames = data.get('frames', [])

    # Locate the previously-uploaded file by trying each allowed extension.
    # We store files by UUID so we need to discover the extension.
    upload_folder = current_app.config['UPLOAD_FOLDER']
    video_path = None
    for ext in current_app.config['ALLOWED_EXTENSIONS']:
        potential_path = os.path.join(upload_folder, f"{file_id}.{ext}")
        if os.path.exists(potential_path):
            video_path = potential_path
            break

    if not video_path:
        return jsonify({'error': 'Video file not found'}), 404

    from app.services.video_service import VideoService
    from app.services.steganography_service import SteganographyService

    try:
        ecc_symbols = int(data.get('ecc_symbols', SteganographyService.RS_ECC_SYMBOLS))
    except (TypeError, ValueError):
        return jsonify({'error': 'ecc_symbols must be an integer'}), 400
    ecc_symbols = max(2, min(ecc_symbols, 30))

    capacity_info = VideoService.calculate_capacity(video_path, frames)
    raw_capacity = capacity_info['total_capacity_bytes']
    # RS(255, 255-n) encodes k source bytes into 255 codeword bytes,
    # so post-ECC capacity = raw * (255 - ecc_symbols) / 255. Encryption adds
    # a fixed ~48 bytes (salt + IV + GCM tag), same constant VideoService uses.
    encryption_overhead = 48
    post_ecc_capacity = int(raw_capacity * (255 - ecc_symbols) / 255)
    usable_capacity = max(0, post_ecc_capacity - encryption_overhead)

    return jsonify({
        'success': True,
        'capacity': {
            **capacity_info,
            'usable_capacity_bytes': usable_capacity,
            'usable_capacity_kb': round(usable_capacity / 1024, 2),
            'usable_capacity_mb': round(usable_capacity / (1024 * 1024), 4),
            # max_characters is a BYTE budget (UTF-8: multibyte chars consume
            # several bytes each); kept for backward compatibility. Prefer
            # max_bytes in new client code.
            'max_characters': usable_capacity,
            'max_bytes': usable_capacity,
        },
        'usable_capacity': usable_capacity,
        'raw_capacity': raw_capacity,
        'ecc_symbols': ecc_symbols,
        'ecc_overhead_bytes': raw_capacity - post_ecc_capacity,
    })


@api_bp.route('/embed', methods=['POST'])
def embed_message():
    """Start embedding a message into video frames.

    Validates required fields and encryption settings, locates the
    uploaded file, then attempts to start a Celery async task.

    Async path (Celery available):
      Returns a task_id the client polls via GET /api/task/<task_id>.
    Sync fallback (Celery/Redis not available):
      Runs the full embed pipeline in-process and returns the result
      immediately, with a 'warning' field indicating degraded mode.
    """
    data = request.get_json(silent=True) or {}

    # Validate that all required fields are present in the request body.
    required_fields = ['file_id', 'message', 'password', 'frames']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    # Validate the requested AES configuration against supported options.
    encryption_strength = data.get('encryption_strength', 'AES-256')
    cipher_mode = data.get('cipher_mode', 'GCM')

    if encryption_strength not in current_app.config['SUPPORTED_KEY_SIZES']:
        return jsonify({'error': 'Invalid encryption strength'}), 400

    if cipher_mode not in current_app.config['SUPPORTED_CIPHER_MODES']:
        return jsonify({'error': 'Invalid cipher mode'}), 400

    # Locate the previously-uploaded video by UUID + extension.
    file_id = data['file_id']
    upload_folder = current_app.config['UPLOAD_FOLDER']
    video_path = None
    for ext in current_app.config['ALLOWED_EXTENSIONS']:
        potential_path = os.path.join(upload_folder, f"{file_id}.{ext}")
        if os.path.exists(potential_path):
            video_path = potential_path
            break

    if not video_path:
        return jsonify({'error': 'Video file not found'}), 404

    # ai_options may contain: content_aware, smart_compression_platform,
    # use_second_lsb, prefer_luma, generate_caption, detect_suspicious, caption_style.
    ai_options = data.get('ai_options') or {}

    from app.services.steganography_service import SteganographyService
    try:
        ecc_symbols = int(data.get('ecc_symbols', SteganographyService.RS_ECC_SYMBOLS))
    except (TypeError, ValueError):
        return jsonify({'error': 'ecc_symbols must be an integer'}), 400
    ecc_symbols = max(2, min(ecc_symbols, 30))

    # Start async task (fallback to sync if Celery broker isn't available).
    # Using .delay() sends the task to the Celery/Redis queue.
    # On connection failure an exception is caught and the pipeline runs
    # synchronously in the web process instead.
    from app.tasks import embed_message_task, run_embed_pipeline
    try:
        task = embed_message_task.delay(
            video_path=video_path,
            message=data['message'],
            password=data['password'],
            frames=data['frames'],
            encryption_strength=encryption_strength,
            cipher_mode=cipher_mode,
            output_folder=current_app.config['OUTPUT_FOLDER'],
            ai_options=ai_options,
            ecc_symbols=ecc_symbols,
        )
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Embedding task started'
        })
    except Exception as e:
        try:
            result = run_embed_pipeline(
                video_path=video_path,
                message=data['message'],
                password=data['password'],
                frames=data['frames'],
                encryption_strength=encryption_strength,
                cipher_mode=cipher_mode,
                output_folder=current_app.config['OUTPUT_FOLDER'],
                ai_options=ai_options,
                ecc_symbols=ecc_symbols,
            )
            return jsonify({
                'success': True,
                'mode': 'sync',
                'result': result,
                'warning': f'Celery unavailable, ran synchronously: {str(e)}'
            })
        except Exception as inner:
            return jsonify({'error': str(inner)}), 500


@api_bp.route('/extract', methods=['POST'])
def extract_message():
    """Start extracting a message from video frames.

    Accepts file_id, password, start_frame, end_frame, and optional
    encryption / AI settings.  Mirrors the embed endpoint's async/sync
    dual-path pattern: tries Celery first, falls back to synchronous.
    """
    data = request.get_json(silent=True) or {}

    required_fields = ['file_id', 'password', 'start_frame', 'end_frame']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    # Locate the stego video by UUID + extension.
    file_id = data['file_id']
    upload_folder = current_app.config['UPLOAD_FOLDER']
    video_path = None
    for ext in current_app.config['ALLOWED_EXTENSIONS']:
        potential_path = os.path.join(upload_folder, f"{file_id}.{ext}")
        if os.path.exists(potential_path):
            video_path = potential_path
            break

    if not video_path:
        return jsonify({'error': 'Video file not found'}), 404

    ai_options = data.get('ai_options') or {}

    from app.services.steganography_service import SteganographyService
    try:
        ecc_symbols = int(data.get('ecc_symbols', SteganographyService.RS_ECC_SYMBOLS))
    except (TypeError, ValueError):
        return jsonify({'error': 'ecc_symbols must be an integer'}), 400
    ecc_symbols = max(2, min(ecc_symbols, 30))

    # Attempt async via Celery; fall back to synchronous execution.
    from app.tasks import extract_message_task, run_extract_pipeline
    try:
        task = extract_message_task.delay(
            video_path=video_path,
            password=data['password'],
            start_frame=data['start_frame'],
            end_frame=data['end_frame'],
            encryption_strength=data.get('encryption_strength', 'AES-256'),
            cipher_mode=data.get('cipher_mode', 'GCM'),
            ai_options=ai_options,
            ecc_symbols=ecc_symbols,
        )
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Extraction task started'
        })
    except Exception as e:
        try:
            result = run_extract_pipeline(
                video_path=video_path,
                password=data['password'],
                start_frame=data['start_frame'],
                end_frame=data['end_frame'],
                encryption_strength=data.get('encryption_strength', 'AES-256'),
                cipher_mode=data.get('cipher_mode', 'GCM'),
                ai_options=ai_options,
                ecc_symbols=ecc_symbols,
            )
            return jsonify({
                'success': True,
                'mode': 'sync',
                'result': result,
                'warning': f'Celery unavailable, ran synchronously: {str(e)}'
            })
        except Exception as inner:
            return jsonify({'error': str(inner)}), 500


@api_bp.route('/ai/select-frames', methods=['POST'])
def ai_select_frames():
    """AI helper: select frames best suited for embedding.

    Uses texture analysis (Laplacian variance) to rank all sampled
    frames and returns the indices of the top-scoring ones.
    High-texture frames hide embedded bits more naturally than flat,
    uniform regions, making detection harder.
    """
    data = request.get_json(silent=True) or {}
    if 'file_id' not in data:
        return jsonify({'error': 'file_id is required'}), 400

    # Number of best frames to return; defaults to 10.
    num_frames = int(data.get('num_frames', 10))

    file_id = data['file_id']
    upload_folder = current_app.config['UPLOAD_FOLDER']
    video_path = None
    for ext in current_app.config['ALLOWED_EXTENSIONS']:
        potential_path = os.path.join(upload_folder, f"{file_id}.{ext}")
        if os.path.exists(potential_path):
            video_path = potential_path
            break

    if not video_path:
        return jsonify({'error': 'Video file not found'}), 404

    from app.services.ai_service import AIService
    try:
        frames = AIService.select_best_frames(video_path, num_frames=num_frames)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'success': True, 'frames': frames})


@api_bp.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get the status of an async task.

    Clients poll this endpoint while waiting for an embed/extract job
    to finish.  The response structure varies by Celery task state:
      PENDING  : task is queued, progress = 0
      PROGRESS : task is running; includes progress % and current_step
      SUCCESS  : task completed; includes the full result dict
      FAILURE  : task failed; includes the error message
    """
    from app.tasks import celery_app

    task = celery_app.AsyncResult(task_id)

    response = {
        'task_id': task_id,
        'status': task.status,
    }

    if task.status == 'PENDING':
        response['progress'] = 0
    elif task.status == 'PROGRESS':
        # task.info is the meta dict passed to self.update_state()
        response['progress'] = task.info.get('progress', 0)
        response['current_step'] = task.info.get('current_step', '')
        if 'frame_current' in task.info:
            response['frame_current'] = task.info['frame_current']
        if 'frame_total' in task.info:
            response['frame_total'] = task.info['frame_total']
    elif task.status == 'SUCCESS':
        response['progress'] = 100
        response['result'] = task.result
    elif task.status == 'FAILURE':
        response['error'] = str(task.result)

    return jsonify(response)


@api_bp.route('/download/<file_id>', methods=['GET'])
def download_output(file_id):
    """Download the processed output video.

    Searches the output directory for a file matching the pattern
    '<file_id>_output.<ext>' across all common video extensions.
    Sends the file as an attachment named 'stego_video.<ext>'.
    """
    output_folder = current_app.config['OUTPUT_FOLDER']

    # Try each extension to find the output file.
    for ext in ['mp4', 'avi', 'mov', 'mkv']:
        filepath = os.path.join(output_folder, f"{file_id}_output.{ext}")
        if os.path.exists(filepath):
            return send_file(
                filepath,
                as_attachment=True,
                download_name=f"stego_video.{ext}"
            )

    return jsonify({'error': 'Output file not found'}), 404


@api_bp.route('/config', methods=['GET'])
def get_config():
    """Get available configuration options.

    Returns the server-side supported values for resolution, encryption
    strength, cipher mode, upload size, and file extensions.
    The frontend uses this to populate its dropdowns dynamically,
    keeping the UI in sync with whatever the server supports.
    """
    return jsonify({
        'resolutions': list(current_app.config['SUPPORTED_RESOLUTIONS'].keys()),
        'encryption_strengths': list(current_app.config['SUPPORTED_KEY_SIZES'].keys()),
        'cipher_modes': current_app.config['SUPPORTED_CIPHER_MODES'],
        'max_file_size': current_app.config['MAX_CONTENT_LENGTH'],
        'allowed_extensions': list(current_app.config['ALLOWED_EXTENSIONS'])
    })
