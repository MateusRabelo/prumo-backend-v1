from app.core.config import settings


def test_family_context_exposes_membership_and_member_counts(client, auth_headers):
    prefix = settings.API_V1_STR
    response = client.post(prefix+'/auth/register', json={
        'email':'family-context@example.com', 'full_name':'Family Context', 'password':'contextpassword123'})
    assert response.status_code == 201
    data = response.json()
    own_id = data['current_family_id']
    user_headers = {'Authorization':'Bearer '+data['access_token'], 'X-Family-Id':own_id}
    invitation = client.post(prefix+'/family/invite', headers=auth_headers,
        json={'invited_email':'family-context@example.com', 'role':'ADMIN'}).json()
    accepted = client.post(prefix+'/family/accept-invite', headers=user_headers, json={'token':invitation['token']})
    assert accepted.status_code == 200
    family_id = accepted.json()['id']
    families = {f['id']:f for f in client.get(prefix+'/auth/my-families', headers=user_headers).json()}
    assert families[own_id]['role'] == 'OWNER'
    assert families[own_id]['members_count'] == 1
    assert families[family_id]['role'] == 'ADMIN'
    assert families[family_id]['members_count'] == 2
    shared_headers = {**user_headers, 'X-Family-Id':family_id}
    current = client.get(prefix+'/family/current', headers=shared_headers)
    assert current.status_code == 200
    assert current.json()['role'] == 'ADMIN'
    assert current.json()['members_count'] == 2
    assert len(client.get(prefix+'/family/members', headers=shared_headers).json()) == 2
    assert client.get(prefix+'/family/current', headers=user_headers).json()['members_count'] == 1
