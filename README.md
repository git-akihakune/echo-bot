# Echo: Chatting with an echo from the past
Echo is a Discord bot that lets you chat with a version of yourself, or anyone you know, in the past. Simply add it to your server, then use the following command to define data cut-off date:
```
/echo @user dd.mm.yyyy
```

The bot will take a while to analyze and process the information. Afterwards, it will start to talk like that specified user on that specified date. The bot will start talking in a channel once you run the command:
```
/echo online
```

To make it stop talking, run the following command in that same channel:
```
/echo offline
```

## How does it work?
1. After the aforementioned command is ran, the bot will read all needed chat data (that is, all messages before that cut-off date), then securely store them in a local file.
2. It will then fine-tune a local LLM model, hosted by Ollama, to try to immitate the specified user's way of chatting.
3. Afterwards, the bot should start chatting in a similar manner to the analyzed person's text. It will try to pace the messages to appear as human as possible, and can even initiate conversations if needed.

## What is it for?
The bot can work retrospectively. For example, if there is someone once dear to you, for any reason, left the server or is unable to message anymore, the bot can give a surprisingly cathartic experience "echoing" that person's past self. Or maybe you want to see how you and your friends have matured over the years, this bot is a fun way to compare your past and present self.