"""
Message validation module for network security
Validates and sanitizes all incoming network messages
"""

import json
from typing import Dict, Any, Optional, Set
from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum message size (1MB)
MAX_MESSAGE_SIZE = 1024 * 1024

# Allowed message types
ALLOWED_MESSAGE_TYPES: Set[str] = {
    'register',
    'heartbeat',
    'batch_result',
    'batch_progress',
    'client_status',
    'handshake_challenge',
    'handshake_response',
    'key_exchange',
    'disconnect'
}

# Required fields for each message type
REQUIRED_FIELDS: Dict[str, Set[str]] = {
    'register': {'type', 'client_info'},
    'heartbeat': {'type', 'client_id'},
    'batch_result': {'type', 'batch_id', 'success'},
    'batch_progress': {'type', 'batch_id', 'progress'},
    'client_status': {'type', 'client_id', 'status'},
    'handshake_response': {'type', 'challenge_response', 'timestamp', 'public_key'},
    'key_exchange': {'type', 'client_id', 'encrypted_key'},
    'disconnect': {'type', 'client_id'}
}

# Validation rules for specific fields
FIELD_VALIDATORS = {
    'progress': lambda v: isinstance(v, (int, float)) and 0 <= v <= 100,
    'success': lambda v: isinstance(v, bool),
    'batch_id': lambda v: isinstance(v, str) and len(v) > 0 and len(v) < 256,
    'client_id': lambda v: isinstance(v, str) and len(v) > 0 and len(v) < 256,
}


class MessageValidationError(Exception):
    """Raised when message validation fails"""
    pass


def validate_message_size(message: str) -> bool:
    """
    Validate message size

    Args:
        message: Raw message string

    Returns:
        True if size is acceptable

    Raises:
        MessageValidationError: If message is too large
    """
    if len(message) > MAX_MESSAGE_SIZE:
        raise MessageValidationError(
            f"Message too large: {len(message)} bytes (max: {MAX_MESSAGE_SIZE})"
        )
    return True


def parse_message(message: str) -> Dict[str, Any]:
    """
    Parse and validate JSON message

    Args:
        message: Raw message string

    Returns:
        Parsed message dictionary

    Raises:
        MessageValidationError: If parsing fails
    """
    try:
        data = json.loads(message)
        if not isinstance(data, dict):
            raise MessageValidationError("Message must be a JSON object")
        return data
    except json.JSONDecodeError as e:
        raise MessageValidationError(f"Invalid JSON: {e}")


def validate_message_type(data: Dict[str, Any]) -> str:
    """
    Validate message type field

    Args:
        data: Parsed message dictionary

    Returns:
        Message type string

    Raises:
        MessageValidationError: If type is invalid
    """
    msg_type = data.get('type')

    if not msg_type:
        raise MessageValidationError("Missing 'type' field")

    if not isinstance(msg_type, str):
        raise MessageValidationError("'type' field must be a string")

    if msg_type not in ALLOWED_MESSAGE_TYPES:
        raise MessageValidationError(f"Unknown message type: {msg_type}")

    return msg_type


def validate_required_fields(data: Dict[str, Any], msg_type: str) -> bool:
    """
    Validate that all required fields are present

    Args:
        data: Parsed message dictionary
        msg_type: Message type

    Returns:
        True if all required fields present

    Raises:
        MessageValidationError: If required fields missing
    """
    required = REQUIRED_FIELDS.get(msg_type, set())

    missing = required - set(data.keys())
    if missing:
        raise MessageValidationError(
            f"Missing required fields for '{msg_type}': {missing}"
        )

    return True


def validate_field_values(data: Dict[str, Any]) -> bool:
    """
    Validate specific field values

    Args:
        data: Parsed message dictionary

    Returns:
        True if all field values are valid

    Raises:
        MessageValidationError: If field values are invalid
    """
    for field, validator in FIELD_VALIDATORS.items():
        if field in data:
            if not validator(data[field]):
                raise MessageValidationError(
                    f"Invalid value for field '{field}': {data[field]}"
                )

    return True


def sanitize_string_fields(data: Dict[str, Any], max_length: int = 1024) -> Dict[str, Any]:
    """
    Sanitize string fields to prevent injection attacks

    Args:
        data: Message dictionary
        max_length: Maximum string length

    Returns:
        Sanitized message dictionary
    """
    sanitized = {}

    for key, value in data.items():
        if isinstance(value, str):
            # Truncate long strings
            if len(value) > max_length:
                logger.warning(f"Truncating field '{key}' from {len(value)} to {max_length} chars")
                value = value[:max_length]

            # Remove null bytes and control characters
            value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')

        elif isinstance(value, dict):
            value = sanitize_string_fields(value, max_length)

        elif isinstance(value, list):
            value = [
                sanitize_string_fields(item, max_length) if isinstance(item, dict) else item
                for item in value
            ]

        sanitized[key] = value

    return sanitized


def validate_message(message: str) -> Dict[str, Any]:
    """
    Comprehensive message validation

    Args:
        message: Raw message string

    Returns:
        Validated and sanitized message dictionary

    Raises:
        MessageValidationError: If validation fails
    """
    try:
        # Size check
        validate_message_size(message)

        # Parse JSON
        data = parse_message(message)

        # Validate message type
        msg_type = validate_message_type(data)

        # Validate required fields
        validate_required_fields(data, msg_type)

        # Validate field values
        validate_field_values(data)

        # Sanitize strings
        data = sanitize_string_fields(data)

        return data

    except MessageValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected validation error: {e}", exc_info=True)
        raise MessageValidationError(f"Validation failed: {e}")


def create_error_response(error_msg: str) -> str:
    """
    Create an error response message

    Args:
        error_msg: Error message

    Returns:
        JSON error response
    """
    response = {
        'type': 'error',
        'error': error_msg
    }
    return json.dumps(response)
