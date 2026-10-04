import requests

BASE_URL = 'http://127.0.0.1:5000'

def test_flow():
    session = requests.Session()
    
    print('1. Testing access to protected dashboard without login...')
    res = session.get(f'{BASE_URL}/dashboard', allow_redirects=False)
    print(f'   Status Code: {res.status_code} (Expected 302 redirect to login)')
    
    print('\n2. Testing Registration...')
    # Register a test user
    reg_data = {
        'name': 'Test User',
        'username': 'testuser123',
        'email': 'testuser123@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    }
    res = session.post(f'{BASE_URL}/register', data=reg_data, allow_redirects=True)
    print(f'   Registration Response Status: {res.status_code}')
    if 'Your account was created' in res.text:
        print('   Registration successful!')
    else:
        print('   Registration note: User might already exist.')

    print('\n3. Testing Password Mismatch Validation...')
    bad_reg_data = {
        'name': 'Bad User',
        'username': 'baduser',
        'email': 'bad@example.com',
        'password': 'password123',
        'confirm_password': 'wrongpassword'
    }
    res = session.post(f'{BASE_URL}/register', data=bad_reg_data)
    if 'Passwords do not match.' in res.text:
        print('   Password mismatch validation works correctly!')

    print('\n4. Testing Login...')
    login_data = {
        'username': 'testuser123',
        'password': 'password123'
    }
    res = session.post(f'{BASE_URL}/login', data=login_data, allow_redirects=True)
    print(f'   Login Response Status: {res.status_code}')
    if 'Welcome back' in res.text or res.url.endswith('/dashboard'):
        print('   Login successful and redirected to dashboard!')

    print('\n5. Testing Protected Dashboard Access (Authenticated)...')
    res = session.get(f'{BASE_URL}/dashboard')
    if 'Test User' in res.text:
        print('   Dashboard successfully accessed and displays user name!')

    print('\n6. Testing Profile Page Access...')
    res = session.get(f'{BASE_URL}/profile')
    if 'testuser123@example.com' in res.text:
        print('   Profile page successfully loaded with user info!')

    print('\n7. Testing Logout...')
    res = session.post(f'{BASE_URL}/logout', allow_redirects=True)
    if 'Login' in res.text:
        print('   Logout successful and redirected to login page!')

    print('\n8. Testing Dashboard Access After Logout...')
    res = session.get(f'{BASE_URL}/dashboard', allow_redirects=False)
    print(f'   Status Code after logout: {res.status_code} (Expected 302 redirect)')

if __name__ == '__main__':
    print('Make sure your Flask app is running in another terminal window (python app.py)!')
    try:
        test_flow()
    except requests.exceptions.ConnectionError:
        print('\nError: Could not connect to Flask app. Please start it first using: python app.py')
