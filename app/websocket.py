"""
WebSocket Events - Real-time progress updates via Socket.IO
"""

from flask_socketio import emit, join_room, leave_room
from app import socketio


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('connected', {'status': 'Connected to VidStega WebSocket'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    pass


@socketio.on('join_task')
def handle_join_task(data):
    """Join a task room to receive updates."""
    task_id = data.get('task_id')
    if task_id:
        join_room(task_id)
        emit('joined', {'task_id': task_id, 'message': 'Subscribed to task updates'})


@socketio.on('leave_task')
def handle_leave_task(data):
    """Leave a task room."""
    task_id = data.get('task_id')
    if task_id:
        leave_room(task_id)
        emit('left', {'task_id': task_id})


def send_progress_update(task_id: str, progress: int, step: str, status: str = 'PROGRESS',
                          frame_current: int = None, frame_total: int = None):
    """Send progress update to all clients subscribed to a task.

    Intended for use with a Celery signal receiver when running with a Redis
    message broker. Clients without push delivery should poll /api/task/<id>,
    which also exposes frame_current and frame_total from Celery task meta.
    """
    payload = {
        'task_id': task_id,
        'progress': progress,
        'current_step': step,
        'status': status,
    }
    if frame_current is not None:
        payload['frame_current'] = frame_current
    if frame_total is not None:
        payload['frame_total'] = frame_total
    socketio.emit('task_progress', payload, room=task_id)


def send_task_complete(task_id: str, result: dict):
    """
    Send task completion notification.
    
    Args:
        task_id: The task ID
        result: Task result dictionary
    """
    socketio.emit('task_complete', {
        'task_id': task_id,
        'result': result
    }, room=task_id)


def send_task_error(task_id: str, error: str):
    """
    Send task error notification.
    
    Args:
        task_id: The task ID
        error: Error message
    """
    socketio.emit('task_error', {
        'task_id': task_id,
        'error': error
    }, room=task_id)
