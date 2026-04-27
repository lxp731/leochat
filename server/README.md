This part allow you to deploy the chatroom server.

### How to start

#### Source code
1. Clone the project
    ```gitexclude
    https://gitee.com/nustarain/chatroom-server.git
    ```

2. Install dependencies

    * For uv
    ```bash
    uv sync
    ```

    * For pip
    ```bash
    pip install -r requirements.txt
    ```

3. Start the server
   ```bash
   source .venv/bin/activate
   python app.py 
   ```
   
The server will start at http://localhost:5000.

#### Docker

```bash
docker compose up -d
```

If everything goes well, you will get a named `chatroom-server-backend` image and a named `chatroom-backend` container.  
Access `http://127.0.0.1:5000` to check.

### Effect picture

![Effect picture](./assets/result.png)