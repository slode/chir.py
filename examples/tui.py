import asyncio
import logging

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Label, Header, Pretty, Tabs, Tab, Markdown
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
        label = Markdown(self.text, classes=f"message {self.role}")
        label.border_title = self.title
        yield label


class ChirpyApp(App):
    CSS_PATH = "styles.css"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client.ChatApiClient(client.url)
        self.current_session = None
        self.sessions = {}

    def get_current_session(self):
        tabs = self.query_one("#session_tabs")
        return tabs.active[4:] if tabs.active is not None else None

    def compose(self) -> ComposeResult:
        yield Header()
        with Tabs(id="session_tabs"):
            ...

        with VerticalScroll(id="results-container"):
            ...

        yield Input(id="message_input", placeholder="Type message")

    async def on_mount(self) -> None:
        """Called when app starts."""
        # Give the input focus, so we can start typing straight away
        self.query_one(Input).focus()
        await self.log_in()
        self.t = asyncio.create_task(self.listen())

    async def add_session(self, session_id: str):
        try:
            self.query_one(f"#tab-{session_id}")
            return
        except Exception:
            ...
        tabs = self.query_one("#session_tabs").add_tab(Tab(session_id, id=f"tab-{session_id}"))
        self.refresh()

    async def join_session(self):
        session = await self.client.chat_session()
        await self.add_session(session["id"])

    async def log_in(self):
        await self.client.guest_login()
        self.user = await self.client.me()

    async def listen(self):
        box = self.query_one("#results-container")
        while True:
            try:
                async for event in self.client.listen():
                    session_id = event["session"]
                    await self.add_session(session_id)

                    source_id = event["origin"]["id"]
                    source = event["origin"]["username"]
                    message = event["message"]
                    role = "question" if source_id == self.user["id"] else "answer"
                    box.mount(
                        MessageBox(text=message.strip(), title=f"{source}@{session_id}", role=role)
                    )
                    box.scroll_end()
                    self.refresh()
            except Exception as e:
                self.log(e)
                await asyncio.sleep(3)

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
        elif word.startswith("/new"):
            await self.join_session()
        elif word.startswith("/logon"):
            cmd, user, password = word.split(" ")
            await self.client.login(user, password)
        elif word.startswith("/invite"):
            cmd, user = word.split(" ")
            await self.client.invite(self.get_current_session(), user.strip())
        elif word.startswith("/sessions"):
            sessions = await self.client.sessions()
            box = self.query_one("#results-container")
            box.mount(Pretty(sessions, name="/sessions", classes="message info"))
            box.scroll_end()
        elif word.startswith("/"):
            return
        else:
            await self.client.post(self.get_current_session(), word)

        self.query_one(Input).clear()


if __name__ == "__main__":
    app = ChirpyApp()
    app.run()
