import os
import urllib.parse
import linkpreview
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


@app.task()
def generate_link_preview(url: str):
    connect(host=os.environ['MONGODB_URI'])
    logger.info(f'Generating link preview for url {url}')
    link_preview = LinkPreview.objects.get(url=url)  # type: LinkPreview
    try:
        processed_url = url
        if _is_twitter(url):
            processed_url = _get_nitter_url(url)

        preview = linkpreview.link_preview(processed_url)

        link_preview.title = preview.title
        link_preview.subtitle = preview.description
        if preview.absolute_image:
            link_preview.image_urls = [preview.absolute_image]
        link_preview.state = LinkPreviewState.Fetched
    except Exception as e:
        logger.warn(str(e))
        link_preview.state = LinkPreviewState.Errored
    link_preview.save()
    disconnect()
