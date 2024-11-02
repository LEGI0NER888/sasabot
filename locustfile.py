from locust import HttpUser, TaskSet, task, between
import json

class UserBehavior(TaskSet):
    @task
    def send_message(self):
        BOT_TOKEN = '7803146105:AAFHw0P1WrAsBuPjHAJ3Gubc88ITyGRPjqs'       # Replace with your bot's token
        CHAT_ID = -1002245994921          # Replace with your chat ID
        FIRST_MESSAGE_ID = 2803               # Replace with your thread's message_thread_id

        url = f"/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "reply_to_message_id": FIRST_MESSAGE_ID,
            "text": "Тестовое сообщение"
        }
        headers = {'Content-Type': 'application/json'}

        with self.client.post(url, json=data, headers=headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Received unexpected status code {response.status_code}: {response.text}")
            else:
                response.success()

class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(0.1, 0.5)  # Adjust to stay within rate limits
    host = "https://api.telegram.org"

