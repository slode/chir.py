import asyncio
import logging

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Label, Header, Pretty
from textual.logging import TextualHandler

from chirpy import client

logging.basicConfig(
    level="DEBUG",
    handlers=[TextualHandler()],
)

logger = logging.getLogger(__name__)


class MessageBox(Widget, can_focus=True):  # type: ignore[call-arg]
    """Box widget for the message."""

    def __init__(self, text: str, title: str, role: str) -> None:
        self.text = text
        self.title = title
        self.role = role
        super().__init__()

    def compose(self) -> ComposeResult:
        """Yield message component."""
        label = Label(self.text, classes=f"message {self.role}")
        label.border_title = self.title
        yield label


class ChirpyApp(App):
    CSS_PATH = "styles.css"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="results-container"):
            ...
        yield Input(id="message_input", placeholder="Type message")

    async def on_mount(self) -> None:
        """Called when app starts."""
        # Give the input focus, so we can start typing straight away
        self.query_one(Input).focus()
        self.t = asyncio.create_task(self.listen())

    async def listen(self):
        self.client = client.ChatApiClient(client.url)
        await self.client.guest_login()
        user = await self.client.me()
        box = self.query_one("#results-container")
        while True:
            try:
                self.chat = await self.client.chat_session()
                self.client.dest = self.chat["id"]
                async for event in self.client.listen():
                    session = event["session"]
                    source_id = event["origin"]["id"]
                    source = event["origin"]["username"]
                    message = event["message"]
                    role = "question" if source_id == user["id"] else "answer"
                    box.mount(
                        MessageBox(text=message.strip(), title=f"{source}@{session}", role=role)
                    )
                    box.scroll_end()
                    self.refresh()
            except Exception as e:
                self.log(e)

    async def on_input_submitted(self) -> None:
        """A coroutine to handle a text changed message."""
        value = self.query_one(Input).value
        if not value:
            return

        self.process_message(value)

    @work(exclusive=True)
    async def process_message(self, word: str) -> None:
        """Looks up a word."""
        if self.client is None:
            return

        if word.startswith("/me"):
            me = await self.client.me()
            box = self.query_one("#results-container")
            box.mount(Pretty(me, name="/me", classes="message info"))
            box.scroll_end()
        elif word.startswith("/new "):
            await self.client.guest_login()
        elif word.startswith("/logon "):
            cmd, user, password = word.split(" ")
            await self.client.login(user, password)
        elif word.startswith("/invite "):
            await self.client.invite(self.client.dest, word[7:].strip())
        elif word.startswith("/sessions"):
            sessions = await self.client.sessions()
            box = self.query_one("#results-container")
            box.mount(Pretty(sessions, name="/sessions", classes="message info"))
            box.scroll_end()
        elif word.startswith("/session "):
            if word[10:]:
                self.client.dest = word[9:].strip()
            else:
                self.client.dest = self.chat["id"]
            box = self.query_one("#results-container")
            box.mount(
                MessageBox(
                    text=f"Now writing to session {self.client.dest}",
                    title="/sessions",
                    role="info",
                )
            )
            box.scroll_end()
        elif word.startswith("/"):
            return
        else:
            await self.client.post(self.client.dest, word)

        self.query_one(Input).clear()


if __name__ == "__main__":
    app = ChirpyApp()
    app.run()
