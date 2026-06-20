"""
WebSocket Events - Real-time progress updates via Socket.IO

This module registers Socket.IO event handlers that allow the server to
push live task-progress updates to browser clients without polling.

Connection lifecycle:
  1. Client loads the page and the JS Socket.IO library connects.
  2. Server fires 'connected' to confirm the handshake.
  3. When a Celery task is started, the client emits 'join_task' with
     the task_id to subscribe to that task's room.
  4. As the Celery task progresses, helper functions in this module
     broadcast 'task_progress', 'task_complete', or 'task_error' to
     every socket in that room.
  5. The client emits 'leave_task' when it no longer needs updates.

Rooms are used (join_room / leave_room) so that updates for task A are
never delivered to clients watching task B.
"""

from flask_socketio import emit, join_room, leave_room
from app import socketio


@socketio.on('connect')
def handle_connect():
    """Handle client connection.

    Fires when a browser establishes a Socket.IO connection.
    Sends a 'connected' acknowledgement so the client knows it
    can start emitting events.
    """
    emit('connected', {'status': 'Connected to VidStega WebSocket'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection.

    Fires when a browser closes its Socket.IO connection (page unload,
    network drop, etc.).  Flask-SocketIO automatically removes the
    socket from all rooms on disconnect, so no explicit cleanup is needed.
    """
    pass


@socketio.on('join_task')
def handle_join_task(data):
    """Join a task room to receive updates.

    The client emits this immediately after receiving a task_id from
    POST /api/embed or /api/extract.  Joining the room keyed by task_id
    ensures that progress events are delivered only to the subscriber(s)
    of that specific task.
    """
    task_id = data.get('task_id')
    if task_id:
        join_room(task_id)
        emit('joined', {'task_id': task_id, 'message': 'Subscribed to task updates'})


@socketio.on('leave_task')
def handle_leave_task(data):
    """Leave a task room.

    Called when the client no longer needs updates (e.g., after the task
    succeeds or the user navigates away).  Prevents unnecessary traffic
    for completed tasks.
    """
    task_id = data.get('task_id')
    if task_id:
        leave_room(task_id)
        emit('left', {'task_id': task_id})


def send_progress_update(task_id: str, progress: int, step: str, status: str = 'PROGRESS'):
    """Send progress update to all clients subscribed to a task.

    Broadcasts a 'task_progress' event to the Socket.IO room identified
    by task_id.  Called by Celery task functions as they move through
    pipeline stages (reading frames -> embedding -> writing video).

    Args:
        task_id: The task ID (also used as the Socket.IO room name)
        progress: Progress percentage (0-100)
        step: Human-readable description of the current pipeline step
        status: Celery task status string ('PROGRESS', 'SUCCESS', etc.)
    """
    socketio.emit('task_progress', {
        'task_id': task_id,
        'progress': progress,
        'current_step': step,
        'status': status
    }, room=task_id)


def send_task_complete(task_id: str, result: dict):
    """Send task completion notification.

    Broadcasts a 'task_complete' event with the full result dictionary.
    The client uses this to display the download link and summary stats
    (bits embedded, frames used, encryption details).

    Args:
        task_id: The task ID / Socket.IO room name
        result: Task result dictionary returned by the pipeline
    """
    socketio.emit('task_complete', {
        'task_id': task_id,
        'result': result
    }, room=task_id)


def send_task_error(task_id: str, error: str):
    """Send task error notification.

    Broadcasts a 'task_error' event when a pipeline step raises an
    unhandled exception.  The client uses this to display an error
    message and re-enable the submit button.

    Args:
        task_id: The task ID / Socket.IO room name
        error: Human-readable error message
    """
    socketio.emit('task_error', {
        'task_id': task_id,
        'error': error
    }, room=task_id)
