import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_health_endpoint():
    """Test the health check endpoint"""
    from app import app
    client = app.test_client()

    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'healthy'
    assert data['service'] == 'Medical Chatbot'


def test_ready_endpoint():
    """Test the readiness check endpoint"""
    from app import app
    client = app.test_client()

    response = client.get('/ready')
    assert response.status_code in [200, 503]  # May fail if services not initialized
    data = response.get_json()
    assert 'status' in data


def test_index_endpoint():
    """Test the main index page"""
    from app import app
    client = app.test_client()

    response = client.get('/')
    assert response.status_code == 200
    assert b'Medical Chatbot' in response.data or b'chatbot' in response.data.lower()


def test_chat_endpoint_empty_message():
    """Test chat endpoint with empty message"""
    from app import app
    client = app.test_client()

    response = client.post('/get', data={'msg': ''})
    assert response.status_code == 400


def test_chat_endpoint_short_message():
    """Test chat endpoint with too short message"""
    from app import app
    client = app.test_client()

    response = client.post('/get', data={'msg': 'hi'})
    assert response.status_code == 400


def test_chat_endpoint_long_message():
    """Test chat endpoint with too long message"""
    from app import app
    client = app.test_client()

    long_message = 'a' * 1001
    response = client.post('/get', data={'msg': long_message})
    assert response.status_code == 400


def test_clear_history_endpoint():
    """Test clearing conversation history"""
    from app import app
    client = app.test_client()

    with client.session_transaction() as sess:
        sess['chat_history'] = [{'question': 'test', 'answer': 'test'}]

    response = client.post('/clear')
    assert response.status_code == 200


def test_get_history_endpoint():
    """Test getting conversation history"""
    from app import app
    client = app.test_client()

    response = client.get('/history')
    assert response.status_code == 200
    data = response.get_json()
    assert 'history' in data


def test_feedback_endpoint():
    """Test feedback submission"""
    from app import app
    client = app.test_client()

    response = client.post('/feedback', data={'feedback': 'up', 'timestamp': '2024-01-01'})
    assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
