from impl.config import config

import logging

if config.DEBUG:
    logging.basicConfig(level=logging.DEBUG)

from persica.context.application import ApplicationContext
from persica.applicationbuilder import ApplicationBuilder

app = (
    ApplicationBuilder()
    .set_application_context_class(ApplicationContext)
    .set_scanner_packages(["impl.core", "impl._spiders"])
    .build()
)


async def run():
    from impl.core._abstract_spider import SpiderManager

    await app.initialize()
    await SpiderManager.start_crawl()


def main():
    app.context.run()
    app._get_runtime_loop().run_until_complete(run())


if __name__ == "__main__":
    main()
