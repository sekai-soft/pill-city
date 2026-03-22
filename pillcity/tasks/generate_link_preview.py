import os
import urllib.parse
import linkpreview
from urllib.parse import unquote
from mongoengine import connect, disconnect
from pillcity.models import LinkPreview, LinkPreviewState
from .celery import app, logger

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
    nitter_https = os.environ['NITTER_HTTPS'] == 'true'
    parsed_url = parsed_url._replace(scheme='https' if nitter_https else 'http')
    return parsed_url.geturl()


def _nitter_base_url() -> str:
    return f"{'https' if os.environ['NITTER_HTTPS'] == 'true' else 'http'}://{os.environ['NITTER_HOST']}"


def _get_nitter_logo_png_url() -> str:
    return _nitter_base_url() + "/logo.png"


def _get_twitter_media_cdn_url(nitter_url: str) -> str:
    suffix = nitter_url.replace(f"{_nitter_base_url()}/pic/", '')
    suffix = unquote(suffix)
    return "https://pbs.twimg.com/" + suffix


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

            if absolute_image:
                link_preview.image_urls = [absolute_image]

        link_preview.state = LinkPreviewState.Fetched

    except Exception as e:
        logger.warn(str(e))
        link_preview.state = LinkPreviewState.Errored

    link_preview.save()
    disconnect()
