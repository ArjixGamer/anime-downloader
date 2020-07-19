import logging
import os

import click
import requests_cache

from anime_downloader import session, util
from anime_downloader.__version__ import __version__
from anime_downloader.sites import get_anime_class, ALL_ANIME_SITES
from anime_downloader.config import Config
from anime_downloader import animeinfo

logger = logging.getLogger(__name__)

echo = click.echo
sitenames = [v[1] for v in ALL_ANIME_SITES]


# NOTE: Don't put defaults here. Add them to the dict in config
@click.command()
@click.argument('anime_url')
@click.option(
    '--episodes', '-e', 'episode_range', metavar='<int>:<int>',
    help="Range of anime you want to download in the form <start>:<end>")
@click.option(
    '--url', '-u', type=bool, is_flag=True,
    help="If flag is set, prints the stream url instead of downloading")
@click.option(
    '--play', 'player', metavar='PLAYER',
    help="Streams in the specified player")
@click.option(
    '--skip-download', is_flag=True,
    help="Retrieve without downloading")
@click.option(
    '--download-dir', metavar='PATH',
    help="Specifiy the directory to download to")
@click.option(
    '--quality', '-q', type=click.Choice(['360p', '480p', '720p', '1080p']),
    help='Specify the quality of episode. Default-720p')
@click.option(
    '--fallback-qualities', '-fq', cls=util.ClickListOption,
    help='Specifiy the order of fallback qualities as a list.')
@click.option(
    '--force-download', '-f', is_flag=True,
    help='Force downloads even if file exists')
@click.option(
    '--file-format', '-ff', default='{anime_title}/{anime_title}_{ep_no}',
    help='Format for how the files to be downloaded be named.',
    metavar='FORMAT STRING'
)
@click.option(
    '--provider',
    help='The anime provider (website) for search.',
    type=click.Choice(sitenames)
)
@click.option(
    '--external-downloader', '-xd',
    help='Use an external downloader command to download. '
         'Use "{aria2}" to use aria2 as downloader. See github wiki.',
    metavar='DOWNLOAD COMMAND'
)
@click.option(
    '--chunk-size',
    help='Chunk size for downloading in chunks(in MB). Use this if you '
         'experience throttling.',
    type=int
)
@click.option(
    '--disable-ssl',
    is_flag=True,
    help='Disable verifying the SSL certificate, if flag is set'
)
@click.option(
    '--choice', '-c',type=int,
    help='Choice to start downloading given anime number '
)
@click.option("--skip-fillers", is_flag=True, help="Skip downloading of fillers.")
@click.pass_context
def command(ctx, anime_url, episode_range, url, player, skip_download, quality,
            force_download, download_dir, file_format, provider,
            external_downloader, chunk_size, disable_ssl, fallback_qualities, choice, skip_fillers):

    query = anime_url[:]
    util.print_info(__version__)

    # Should maybe make this a whole new command?
    fallback_providers = Config['dl']['fallback_providers']
    fallback_providers.insert(0, provider)

    # TODO: keep track on episodes so the next provider can take over on the current episode
    # TODO: make the downloaded title consistent, (maybe use the title from MAL) if another 
    # provider takes over it uses a different naming scheme
    # TODO: Proper provider handling. If the episode is correctly downloaded it should reset the
    # fallback list. The current for loop will probably be prone to breakage under longer downloads 
    # (One Piece) due to this.
    # TODO: Allow the user to skip to the next provider in search select (util.py)

    # TODO: flag/config to turn off this
    # TODO: make the function used based on config (MAL or Anilist)
    episode_count = animeinfo.search_anilist(query)[0].episodes - 1
    episode_range = util.parse_episode_range(episode_count, episode_range)
    episode_range_split = episode_range.split(':')

    for _episode in range(int(episode_range_split[0]), int(episode_range_split[-1])+1):
        episode_range = str(_episode)
        for provider in fallback_providers:
            #logger.info('Current provider: {}'.format(provider))
            # A copy because _anime_url gets modified
            _anime_url = anime_url[:]
            """ Download the anime using the url or search for it.
            """
            # TODO: Replace by factory
            cls = get_anime_class(_anime_url)

            disable_ssl = cls and cls.__name__ == 'Masterani' or disable_ssl
            session.get_session().verify = not disable_ssl

            if not cls:
                _anime_url = util.search(_anime_url, provider, choice)
                if not _anime_url:
                    continue

                cls = get_anime_class(_anime_url)

            try:
                anime = cls(_anime_url, quality=quality,
                            fallback_qualities=fallback_qualities)
            
            # I have yet to investigate all errors this can output
            # No sources found gives error which exits the script
            except:
                continue

            logger.info('Found anime: {}'.format(anime.title))
            try:
                animes = util.parse_ep_str(anime, episode_range)
            except RuntimeError:
                logger.error('No episode found with index {}'.format(episode_range))
                continue
            # TODO:
            # Two types of plugins:
            #   - Aime plugin: Pass the whole anime
            #   - Ep plugin: Pass each episode
            if url or player:
                skip_download = True

            if download_dir and not skip_download:
                logger.info('Downloading to {}'.format(os.path.abspath(download_dir)))
            if skip_fillers:
                fillers = util.get_filler_episodes(query)
            for episode in animes:
                if skip_fillers and fillers:
                    if episode.ep_no in fillers:
                        logger.info("Skipping episode {} because it is a filler.".format(episode.ep_no))
                        continue
                
                if url:
                    util.print_episodeurl(episode)

                if player:
                    util.play_episode(episode, player=player)

                if not skip_download:
                    if external_downloader:
                        logging.info('Downloading episode {} of {}'.format(
                            episode.ep_no, anime.title)
                        )
                        util.external_download(external_downloader, episode,
                                               file_format, path=download_dir)
                        continue
                    if chunk_size is not None:
                        chunk_size *= 1e6
                        chunk_size = int(chunk_size)
                    with requests_cache.disabled():
                        episode.download(force=force_download,
                                         path=download_dir,
                                         format=file_format,
                                         range_size=chunk_size)
                    print()
            break
