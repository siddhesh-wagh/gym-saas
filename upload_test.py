import requests

url = "http://127.0.0.1:5000/upload-csv"

files = {
    'file': open('members.csv', 'rb')
}

data = {
    'gym_id': 1,
    'plan_id': 1
}

response = requests.post(url, files=files, data=data)

print("Status:", response.status_code)
print("Response:", response.text)

