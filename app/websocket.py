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


def send_progress_update(task_id: str, progress: int, step: str, status: str = 'PROGRESS'):
    """
    Send progress update to all clients subscribed to a task.
    
    Args:
        task_id: The task ID
        progress: Progress percentage (0-100)
        step: Current step description
        status: Task status
    """
    socketio.emit('task_progress', {
        'task_id': task_id,
        'progress': progress,
        'current_step': step,
        'status': status
    }, room=task_id)


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
