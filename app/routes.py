"""
Flask Routes - Main and API blueprints
"""

import os
import uuid
from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)


def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def ensure_directories():
    """Ensure upload and output directories exist."""
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(current_app.config['OUTPUT_FOLDER'], exist_ok=True)


# ============= Main Routes =============

@main_bp.route('/')
def index():
    """Render the main application page."""
    return render_template('index.html')


@main_bp.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'version': '2.0.0'})


# ============= API Routes =============

@api_bp.route('/upload', methods=['POST'])
def upload_video():
    """Upload a video file for processing."""
    ensure_directories()
    
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, avi, mov, mkv, webm'}), 400
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{file_id}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    
    file.save(filepath)
    
    # Get video info
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
    """Calculate embedding capacity for a video."""
    data = request.get_json()
    
    if not data or 'file_id' not in data:
        return jsonify({'error': 'file_id is required'}), 400
    
    file_id = data['file_id']
    frames = data.get('frames', [])
    
    # Find the uploaded file
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
    capacity = VideoService.calculate_capacity(video_path, frames)
    
    return jsonify({
        'success': True,
        'capacity': capacity
    })


@api_bp.route('/embed', methods=['POST'])
def embed_message():
    """Start embedding a message into video frames."""
    data = request.get_json(silent=True) or {}
    
    required_fields = ['file_id', 'message', 'password', 'frames']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate encryption settings
    encryption_strength = data.get('encryption_strength', 'AES-256')
    cipher_mode = data.get('cipher_mode', 'GCM')
    
    if encryption_strength not in current_app.config['SUPPORTED_KEY_SIZES']:
        return jsonify({'error': 'Invalid encryption strength'}), 400
    
    if cipher_mode not in current_app.config['SUPPORTED_CIPHER_MODES']:
        return jsonify({'error': 'Invalid cipher mode'}), 400
    
    # Find the uploaded file
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

    # Start async task (fallback to sync if Celery broker isn't available)
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
            ai_options=ai_options
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
                ai_options=ai_options
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
    """Start extracting a message from video frames."""
    data = request.get_json(silent=True) or {}
    
    required_fields = ['file_id', 'password', 'start_frame', 'end_frame']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Find the uploaded file
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

    # Start async task (fallback to sync if Celery broker isn't available)
    from app.tasks import extract_message_task, run_extract_pipeline
    try:
        task = extract_message_task.delay(
            video_path=video_path,
            password=data['password'],
            start_frame=data['start_frame'],
            end_frame=data['end_frame'],
            encryption_strength=data.get('encryption_strength', 'AES-256'),
            cipher_mode=data.get('cipher_mode', 'GCM'),
            ai_options=ai_options
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
                ai_options=ai_options
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
    """AI helper: select frames best suited for embedding."""
    data = request.get_json(silent=True) or {}
    if 'file_id' not in data:
        return jsonify({'error': 'file_id is required'}), 400

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
    """Get the status of an async task."""
    from app.tasks import celery_app
    
    task = celery_app.AsyncResult(task_id)
    
    response = {
        'task_id': task_id,
        'status': task.status,
    }
    
    if task.status == 'PENDING':
        response['progress'] = 0
    elif task.status == 'PROGRESS':
        response['progress'] = task.info.get('progress', 0)
        response['current_step'] = task.info.get('current_step', '')
    elif task.status == 'SUCCESS':
        response['progress'] = 100
        response['result'] = task.result
    elif task.status == 'FAILURE':
        response['error'] = str(task.result)
    
    return jsonify(response)


@api_bp.route('/download/<file_id>', methods=['GET'])
def download_output(file_id):
    """Download the processed output video."""
    output_folder = current_app.config['OUTPUT_FOLDER']
    
    # Look for output file
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
    """Get available configuration options."""
    return jsonify({
        'resolutions': list(current_app.config['SUPPORTED_RESOLUTIONS'].keys()),
        'encryption_strengths': list(current_app.config['SUPPORTED_KEY_SIZES'].keys()),
        'cipher_modes': current_app.config['SUPPORTED_CIPHER_MODES'],
        'max_file_size': current_app.config['MAX_CONTENT_LENGTH'],
        'allowed_extensions': list(current_app.config['ALLOWED_EXTENSIONS'])
    })
