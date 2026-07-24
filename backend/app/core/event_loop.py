import asyncio
import sys


def configure_windows_selector_event_loop() -> None:
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is not None and not isinstance(
        asyncio.get_event_loop_policy(), selector_policy
    ):
        asyncio.set_event_loop_policy(selector_policy())
