import asyncio
import aiohttp
import logging

try:
    import httpx
except ImportError:
    raise ImportError("Please install httpx with 'pip install httpx' ")


from textual import work, log
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Container, Horizontal
from textual.widget import Widget
from textual.widgets import Input, Label, Static, Welcome, Header, Footer
from textual.logging import TextualHandler

from chirpy import client

logging.basicConfig(
    level="DEBUG",
    handlers=[TextualHandler()],
)

log = logging.getLogger(__name__)


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


class FocusableContainer(Container, can_focus=True):  # type: ignore[call-arg]
    """Focusable container widget."""


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
                chat = await self.client.chat_session()
                self.client.dest = chat["id"]
                async for event in self.client.listen():
                    session = event["session"]
                    source_id = event["origin"]["id"]
                    source = event["origin"]["username"]
                    message = event["message"]
                    role = "question" if source_id == user["id"] else "answer"
                    box.mount(MessageBox(text=message.strip(), title=source, role=role))
                    box.scroll_end()
                    self.refresh()
            except Exception as e:
                self.log(e)

    async def on_input_submitted(self) -> None:
        """A coroutine to handle a text changed message."""
        value = self.query_one(Input).value
        self.lookup_word(value)
        self.query_one(Input).clear()

    @work(exclusive=True)
    async def lookup_word(self, word: str) -> None:
        """Looks up a word."""
        if self.client is not None:
            await self.client.post(self.client.dest, word)


if __name__ == "__main__":
    app = ChirpyApp()
    app.run()
