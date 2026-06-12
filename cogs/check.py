from google import genai
# APIキーは適宜入力してください
client = genai.Client(api_key="AQ.Ab8RN6LGcyYprLdh1uUj9mmiwj17ru-AbBZE1MkOm6MSjzl8Ow")
for m in client.models.list():
    print(m.name)