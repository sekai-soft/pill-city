import os
import urllib.parse
import linkpreview
from urllib.parse import unquote
from mongoengine import connect, disconnect
from pillcity.models import LinkPreview, LinkPreviewState
from .celery import app, logger

# Twitter
twitter_domains = [
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "x.com",
    "www.x.com",
    "mobile.x.com"
]


def _is_twitter(url: str) -> bool:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.netloc in twitter_domains:
        return True
    return False


def _get_nitter_url(url: str) -> str:
    parsed_url = urllib.parse.urlparse(url)
    parsed_url = parsed_url._replace(netloc=os.environ['NITTER_HOST'])
    https = os.environ['NITTER_HTTPS'] == 'true'
    parsed_url = parsed_url._replace(scheme='https' if https else 'http')
    return parsed_url.geturl()


def _nitter_base_url() -> str:
    return f"{'https' if os.environ['NITTER_HTTPS'] == 'true' else 'http'}://{os.environ['NITTER_HOST']}"


def _get_nitter_logo_png_url() -> str:
    return _nitter_base_url() + "/logo.png"


def _get_twitter_media_cdn_url(nitter_url: str) -> str:
    suffix = nitter_url.replace(f"{_nitter_base_url()}/pic/", '')
    suffix = unquote(suffix)
    return "https://pbs.twimg.com/" + suffix


# YouTube
youtube_domains = [
    "youtu.be",
    "m.youtube.com",
    "youtube.com",
    "www.youtube.com",
]


def _is_youtube(url: str) -> bool:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.netloc in youtube_domains:
        return True
    return False


def _get_invidious_url(url: str) -> str:
    parsed_url = urllib.parse.urlparse(url)
    parsed_url = parsed_url._replace(netloc=os.environ['INVIDIOUS_HOST'])
    https = os.environ['INVIDIOUS_HTTPS'] == 'true'
    parsed_url = parsed_url._replace(scheme='https' if https else 'http')
    return parsed_url.geturl()


def _get_youtube_thumbnail_cdn_url(invidious_url: str) -> str:
    parsed_url = urllib.parse.urlparse(invidious_url)
    video_id = urllib.parse.parse_qs(parsed_url.query)['v'][0]
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


@app.task()
def generate_link_preview(url: str):
    connect(host=os.environ['MONGODB_URI'])
    logger.info(f'Generating link preview for url {url}')
    link_preview = LinkPreview.objects.get(url=url)  # type: LinkPreview
    try:
        processed_url = url
        is_twitter = _is_twitter(url)
        if is_twitter:
            processed_url = _get_nitter_url(url)
        is_youtube = _is_youtube(url)
        if is_youtube:
            processed_url = _get_invidious_url(url)

        preview = linkpreview.link_preview(processed_url)

        link_preview.title = preview.title
        link_preview.subtitle = preview.description

        if preview.absolute_image:
            absolute_image = preview.absolute_image

            if is_twitter:
                if absolute_image == _get_nitter_logo_png_url():
                    absolute_image = None
                else:
                    absolute_image = _get_twitter_media_cdn_url(absolute_image)
            
            if is_youtube:
                absolute_image = _get_youtube_thumbnail_cdn_url(processed_url)

            if absolute_image:
                link_preview.image_urls = [absolute_image]

        link_preview.state = LinkPreviewState.Fetched

    except Exception as e:
        logger.warn(str(e))
        link_preview.state = LinkPreviewState.Errored

    link_preview.save()
    disconnect()
