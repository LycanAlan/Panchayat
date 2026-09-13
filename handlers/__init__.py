"""Deployment entry points for the paths that are not request-scoped.

`app.py` is the request path on AgentCore Runtime. These are the other two:

    temporal.py   EventBridge Scheduler -> Lambda -> Watchdog
    (ambient)     DynamoDB Streams -> Lambda -> Pattern Watch  [Kartik's lane]

They are thin ON PURPOSE. A handler translates one event shape into one agent
call and does nothing else -- no business logic, so nothing here needs a
different test than the agent already has.

And one that is not a path at all, only a door to the first:

    web_api.py    Lambda Function URL -> the built site, and /api -> app.py
"""
