This part provide a chatroom client for linux users with command-line.

### How to start

1. Build the docker image, slove the network stuff by yourself.

```bash
docker build -t chatroom-cli:latest .
```

2. Just run this command, the container won't run, but it's not a error.

```bash
docker run -dit --name chatroom-cli chatroom-cli:latest
```

3. Copy the executable file form container.

```bash
docker cp chatroom-cli:/app/app.bin .
```

4. Directly run app.bin

```bash
./app.bin
```

### Effect picture

![Effect picture](./assets/result.png)