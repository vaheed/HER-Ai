"""Twitter integration tools for HER AI Assistant.

Supports:
- Posting tweets based on config instructions
- Following users
- Reading timeline
- Liking tweets
- Replying to tweets
"""

import logging
import os
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class TwitterTool(BaseTool):
    """Twitter operations tool using Twitter API v2."""

    name: str = "twitter_operation"
    description: str = (
        "Perform Twitter operations: tweet, follow users, read timeline, like tweets, reply. "
        "Requires Twitter API credentials configured in environment variables."
    )

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        self.bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

    def _run(
        self,
        operation: str,
        text: str = "",
        user_id: str = "",
        tweet_id: str = "",
        **_: Any,
    ) -> str:
        """Execute Twitter operation."""
        if not self._has_credentials():
            return "❌ Twitter credentials not configured. Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET, or TWITTER_BEARER_TOKEN"

        try:
            import tweepy

            client = self._get_client()
            if not client:
                return "❌ Failed to initialize Twitter client"

            operation = operation.lower()

            if operation == "tweet":
                return self._tweet(client, text)
            elif operation == "follow":
                return self._follow(client, user_id)
            elif operation == "timeline":
                return self._read_timeline(client)
            elif operation == "like":
                return self._like_tweet(client, tweet_id)
            elif operation == "reply":
                return self._reply_tweet(client, tweet_id, text)
            else:
                return f"❌ Unknown operation: {operation}. Supported: tweet, follow, timeline, like, reply"

        except ImportError:
            return "❌ tweepy package not installed. Install with: pip install tweepy"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Twitter operation failed")
            return f"❌ Twitter operation failed: {exc}"

    def _has_credentials(self) -> bool:
        """Check if Twitter credentials are available."""
        return bool(
            (self.api_key and self.api_secret and self.access_token and self.access_token_secret)
            or self.bearer_token
        )

    def _get_client(self):
        """Initialize Twitter API client."""
        try:
            import tweepy

            if self.bearer_token:
                return tweepy.Client(bearer_token=self.bearer_token)
            elif self.api_key and self.api_secret and self.access_token and self.access_token_secret:
                return tweepy.Client(
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_token_secret,
                )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create Twitter client: %s", exc)
            return None

    def _tweet(self, client, text: str) -> str:
        """Post a tweet."""
        if not text.strip():
            return "❌ Tweet text cannot be empty"

        try:
            response = client.create_tweet(text=text[:280])  # Twitter limit
            tweet_id = response.data["id"]
            return f"✅ Tweet posted successfully! Tweet ID: {tweet_id}\n📝 Content: {text[:280]}"
        except Exception as exc:  # noqa: BLE001
            return f"❌ Failed to post tweet: {exc}"

    def _follow(self, client, user_id: str) -> str:
        """Follow a user."""
        if not user_id.strip():
            return "❌ User ID is required"

        try:
            # Get authenticated user ID
            me = client.get_me()
            my_user_id = me.data.id

            client.follow_user(target_user_id=user_id, user_auth=True)
            return f"✅ Successfully followed user: {user_id}"
        except Exception as exc:  # noqa: BLE001
            return f"❌ Failed to follow user: {exc}"

    def _read_timeline(self, client, max_results: int = 10) -> str:
        """Read home timeline."""
        try:
            me = client.get_me()
            my_user_id = me.data.id

            tweets = client.get_home_timeline(
                user_id=my_user_id,
                max_results=min(max_results, 100),
                tweet_fields=["created_at", "author_id", "public_metrics"],
            )

            if not tweets.data:
                return "📭 No tweets in timeline"

            lines = ["📱 Home Timeline:\n"]
            for tweet in tweets.data[:max_results]:
                author_id = tweet.author_id if hasattr(tweet, "author_id") else "unknown"
                created = tweet.created_at.strftime("%Y-%m-%d %H:%M") if hasattr(tweet, "created_at") else "unknown"
                text = tweet.text[:100] + "..." if len(tweet.text) > 100 else tweet.text
                lines.append(f"  • [{created}] @{author_id}: {text}")

            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return f"❌ Failed to read timeline: {exc}"

    def _like_tweet(self, client, tweet_id: str) -> str:
        """Like a tweet."""
        if not tweet_id.strip():
            return "❌ Tweet ID is required"

        try:
            me = client.get_me()
            my_user_id = me.data.id

            client.like(tweet_id=tweet_id, user_auth=True)
            return f"✅ Liked tweet: {tweet_id}"
        except Exception as exc:  # noqa: BLE001
            return f"❌ Failed to like tweet: {exc}"

    def _reply_tweet(self, client, tweet_id: str, text: str) -> str:
        """Reply to a tweet."""
        if not tweet_id.strip():
            return "❌ Tweet ID is required"
        if not text.strip():
            return "❌ Reply text cannot be empty"

        try:
            response = client.create_tweet(text=text[:280], in_reply_to_tweet_id=tweet_id)
            reply_id = response.data["id"]
            return f"✅ Reply posted! Reply ID: {reply_id}\n📝 Content: {text[:280]}"
        except Exception as exc:  # noqa: BLE001
            return f"❌ Failed to reply: {exc}"


class TwitterConfigTool(BaseTool):
    """Read and apply Twitter configuration instructions."""

    name: str = "twitter_config"
    description: str = (
        "Read Twitter configuration and execute scheduled Twitter actions based on instructions. "
        "Supports auto-tweeting, auto-following, and scheduled content posting."
    )

    def _run(self, action: str = "read", **_: Any) -> str:
        """Read or apply Twitter config."""
        try:
            from utils.config_paths import resolve_config_file
            import yaml

            config_path = resolve_config_file("twitter.yaml")
            if not config_path.exists():
                return "ℹ️ No Twitter configuration found. Create config/twitter.yaml to enable Twitter features."

            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            if action == "read":
                return self._format_config(config)
            elif action == "execute":
                return self._execute_config(config)
            else:
                return f"❌ Unknown action: {action}. Use 'read' or 'execute'"

        except Exception as exc:  # noqa: BLE001
            logger.exception("Twitter config operation failed")
            return f"❌ Failed to process Twitter config: {exc}"

    def _format_config(self, config: dict) -> str:
        """Format config for display."""
        lines = ["📋 Twitter Configuration:\n"]

        auto_tweet = config.get("auto_tweet", {})
        if auto_tweet.get("enabled"):
            lines.append("✅ Auto-tweet: Enabled")
            lines.append(f"   Schedule: {auto_tweet.get('schedule', 'not set')}")
            lines.append(f"   Template: {auto_tweet.get('template', 'not set')[:50]}...")
        else:
            lines.append("❌ Auto-tweet: Disabled")

        auto_follow = config.get("auto_follow", {})
        if auto_follow.get("enabled"):
            lines.append("✅ Auto-follow: Enabled")
            lines.append(f"   Keywords: {', '.join(auto_follow.get('keywords', []))}")
        else:
            lines.append("❌ Auto-follow: Disabled")

        return "\n".join(lines)

    def _execute_config(self, config: dict) -> str:
        """Execute configured Twitter actions."""
        results = []

        # Auto-tweet if enabled
        auto_tweet = config.get("auto_tweet", {})
        if auto_tweet.get("enabled"):
            template = auto_tweet.get("template", "")
            if template:
                twitter_tool = TwitterTool()
                result = twitter_tool._run(operation="tweet", text=template)
                results.append(f"Auto-tweet: {result}")

        # Auto-follow if enabled
        auto_follow = config.get("auto_follow", {})
        if auto_follow.get("enabled"):
            keywords = auto_follow.get("keywords", [])
            results.append(f"Auto-follow: Would search for users with keywords: {', '.join(keywords)}")

        if not results:
            return "ℹ️ No Twitter actions configured to execute"

        return "\n".join(results)
