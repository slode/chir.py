TOKEN=$(curl -XPOST 'http://localhost:8000/guest-token' | jq -r '.access_token')
SESSION=$(curl -XPOST 'http://localhost:8000/chat' -H "Authorization: Bearer $TOKEN" | jq -r '.id')
echo $TOKEN
echo $SESSION
curl -s "http://localhost:8000/chat/listen" -H "Authorization: Bearer $TOKEN"
