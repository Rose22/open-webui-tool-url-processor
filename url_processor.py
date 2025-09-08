"""
title: URL Processor
author: Rose22
author_url: https://github.com/Rose22
git_url: https://github.com/Rose22/open-webui-tool-url-processor
description: processes any link you throw at the AI, from websites to images to archives to scripts to anything inbetween.
requirements: bs4, xmltodict, pypdf, tinytag, moviepy, youtube-transcript-api, rarfile
version: 1.4
license: GPL3
"""

#  Copyright (C) 2025  Rose22
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

####
# NOTE: for the youtube processor to work, you have to use the very latest version of youtube-transcript-api.
# as of the time of writing this, that's only available on their github, and the version on PIP is out of date!
# so please manually install that version for youtube Processing to work.

from pydantic import BaseModel, Field
import os
import asyncio
import aiohttp


async def emit_status(event_emitter, description: str, done: bool):
    if event_emitter:
        await event_emitter(
            {
                "type": "status",
                "data": {
                    "description": description,
                    "done": done,
                },
            }
        )


async def emit_message(event_emitter, content: str):
    if event_emitter:
        await event_emitter(
            {
                "type": "message",
                "data": {"content": content},
            }
        )


class Tools:
    class Valves(BaseModel):
        user_agent: str = Field(
            default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
            description="the user agent to use for all web requests. the default should suffice!",
        )
        multiple_urls_description_prompt: str = Field(
            default="describe what was found. include links to the sources.",
            description="a system prompt that defines how the AI should present information from multiple urls at once, considering data often exceed context size.",
        )

    def __init__(self):
        self.valves = self.Valves()

        pass

    async def process_url(
        self, url: str, __user__: dict, __event_emitter__=None
    ) -> str:
        """
        processes any url user may have provided.

        will process:
        - websites
        - html
        - xml
        - markdown
        - source code
        - scripts
        - json
        - yaml
        - ini
        - csv
        - logs
        - images
        - music
        - videos
        - PDFs
        - documents
        - archive files such as zip and rar
        - youtube videos
        - executables
        """

        # import only if this function is called, saves time and memory when the AI isn't actually using this call.
        import urllib

        # we define functions inside this method so that the AI can't call them

        async def _request(url):
            async with aiohttp.ClientSession(
                headers={"User-Agent": self.valves.user_agent}
            ) as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        raise Exception(f"Request failed with status {response.status}")
                    return await response.read()

        def remove_duplicates(lst: list):
            # removes duplicates from a list

            new_lst = []
            for item in lst:
                if item not in new_lst:
                    new_lst.append(item)
            return new_lst

        async def process_webpage(html, list_urls: bool = False):
            # uses beautifulsoup to scrape a webpage

            output = {}

            import re
            from bs4 import BeautifulSoup

            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

            await emit_status(__event_emitter__, "Processing website..", False)

            # we can usually get plenty of information from just the title, headers and paragraphs of a page!
            try:
                output["title"] = soup.find("title").get_text().strip()
            except AttributeError:
                # no title found
                pass

            output["headers"] = []
            for header in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                output["headers"].append(header.get_text().strip())
            if not output["headers"]:
                del output["headers"]

            output["paragraphs"] = []
            for para in soup.find_all("p"):
                output["paragraphs"].append(para.get_text().strip())
            if not output["paragraphs"]:
                del output["paragraphs"]

            output["images"] = []
            for image in soup.find_all("img"):
                if image.get("alt"):
                    output["images"].append(image.get("alt"))

            if not output["images"]:
                del output["images"]

            if list_urls:
                output["urls"] = []
                for a in soup.find_all("a", href=True):
                    output["urls"].append(a["href"])
                if not output["urls"]:
                    del output["urls"]

            # remove duplicates
            for category in list(output.keys()):
                if category == "title":
                    continue

                output[category] = remove_duplicates(output[category])

            # but not always...
            if "headers" not in output.keys() and "paragraphs" not in output.keys():
                # if nothing was found, first, fall back on common CSS classes
                output["classes"] = {}
                for class_name in (
                    "content",
                    "description",
                    "title",
                    "text",
                    "article",
                ):
                    output["classes"][class_name] = []
                    for element in soup.find_all(
                        class_=re.compile(rf"\b{class_name}\b")
                    ):
                        if element.text != "":
                            output["classes"][class_name].append(element.text)
                    # also get elements by id
                    for element in soup.find_all(id=re.compile(rf"\b{class_name}\b")):
                        if element.text != "":
                            output["classes"][class_name].append(element.text)

                    if not output["classes"][class_name]:
                        # no data found for the class? just delete it from the response
                        del output["classes"][class_name]
                        continue

                    # remove duplicates
                    output["classes"][class_name] = remove_duplicates(
                        output["classes"][class_name]
                    )

                if not output["classes"]:
                    # still nothing?
                    # then fall back on links if nothing could be extracted from the other html elements.
                    # this is a last resort because it tends to be a lot of data to process

                    del output["classes"]

                    output["urls"] = []
                    for a in soup.find_all("a", href=True):
                        output["urls"].append(a["href"])

                    # remove duplicate links
                    output["urls"] = remove_duplicates(output["urls"])

                    if not output["urls"]:
                        # alright, theres no saving this one. at least we have a title!
                        del output["urls"]

                        output["message"] = (
                            "nothing could be scraped from the page! use a web search tool call to find more information about this website."
                        )

            await emit_status(__event_emitter__, "Processed website", True)
            return output

        async def process_search(url):
            html = await _request(url)

            output = []

            import re
            from bs4 import BeautifulSoup

            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

            await emit_status(__event_emitter__, "Processing search..", False)

            urls = []

            headers = []
            for header in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                headers.append(header.get_text().strip())

            for a in soup.find_all("a", href=True):
                urls.append(a["href"])

            urls = remove_duplicates(urls)

            processed_urls = []
            for url in urls:
                # get rid of duckduckgo's garbage
                url = url.replace("//duckduckgo.com", "")
                url = url.replace("/l/?uddg=", "")

                url = urllib.parse.unquote(url)

                # more garbage
                url = url.split("&rut")[0]

                if url in ["/html/", "/feedback.html"]:
                    continue

                processed_urls.append(url)

            return await self.process_multiple_urls(processed_urls, __user__)

        async def process_domains(domain, url):
            if "youtube" in domain and "watch" in url or "youtu.be" in domain:
                # this is a youtube link. try and get the transcript!
                import youtube_transcript_api

                err = None

                await emit_status(
                    __event_emitter__, "Processing youtube video..", False
                )

                # get video transcript using a python module
                ytt_api = youtube_transcript_api.YouTubeTranscriptApi()

                parsed = urllib.parse.urlparse(url)
                # how to get the video id depends on if it's youtube or youtu.be
                if "youtube" in domain:
                    query = urllib.parse.parse_qs(parsed.query)
                    video_id = query.get("v", [None])[0]
                    if not video_id:
                        err = "No video id found in URL"
                elif domain == "youtu.be":
                    video_id = parsed.path.lstrip("/")

                try:
                    transcript_obj = ytt_api.fetch(video_id)
                except:
                    # that likely means a transcript wasn't available in the preferred language.
                    # so fall back on the first one available:
                    try:
                        transcript_obj_list = list(ytt_api.list(video_id))
                        transcript_obj = transcript_obj_list[0].fetch()
                    except Exception as e:
                        err = f"couldn't find subtitles. tell the user the title of the video!"

                # get video title using beautifulsoup
                from bs4 import BeautifulSoup

                html = await _request(url)
                soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

                title = soup.find("title").get_text().strip()

                transcript_dict = {"type": "youtube", "title": title}

                if not err:
                    transcript = []
                    for snippet in transcript_obj:
                        transcript.append(snippet.text)
                    transcript_text = " ".join(transcript)

                    transcript_dict["transcript"] = {
                        "language": f"({transcript_obj.language_code}) {transcript_obj.language}",
                        "auto_generated": transcript_obj.is_generated,
                        "content": transcript_text,
                        "words": len(transcript_text.split(" ")),
                    }
                else:
                    transcript_dict["error"] = err

                await emit_status(__event_emitter__, "Processed youtube video", True)
                return transcript_dict
            elif "duckduckgo" in domain:
                return await process_search(url)

        async def process_text(file_content):
            return file_content.decode(errors="replace")

        async def process_image(file_content):
            import base64

            return base64.b64encode(file_content).decode("utf-8")

        async def process_xml(file_content):
            import xmltodict

            return xmltodict.parse(file_content.decode(errors="replace"))

        async def process_yaml(file_content):
            import yaml
            import json

            try:
                return json.dumps(
                    yaml.safe_load(file_content.decode(errors="replace")),
                    indent=2,
                )
            except yaml.YAMLError as e:
                return f"YAML Error: {e}"

        async def process_csv(file_content):
            from io import StringIO
            import csv

            output = []
            for row in csv.reader(StringIO(file_content.decode(errors="replace"))):
                output.append(list(row))

            return output

        async def process_pdf(file_content):
            from io import BytesIO
            import pypdf

            pdf_reader = pypdf.PdfReader(BytesIO(file_content))
            pages_text = []
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            return pages_text

        async def process_audio(file_content):
            from io import BytesIO
            import tinytag

            tag_reader = tinytag.TinyTag.get(file_obj=BytesIO(file_content))
            return tag_reader.as_dict()

        async def process_video(file_content):
            import moviepy
            import tempfile

            # moviepy is stubborn and absolutely insists on a file name, not a file object
            # so let's write it to a file i guess...
            tmp_path = ""
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            clip = None
            try:
                clip = moviepy.VideoFileClip(tmp_path)

                output = {
                    "duration": clip.duration,
                    "fps": clip.fps,
                    "width": clip.w,
                    "height": clip.h,
                    "has_audio": clip.audio is not None,
                    "audio_channels": clip.audio.nchannels if clip.audio else None,
                    "audio_fps": clip.audio.fps if clip.audio else None,
                    "misc": getattr(clip.reader, "infos", None),
                }
            finally:
                if clip:
                    clip.close()
                os.remove(tmp_path)

            return output

        async def process_zip(file_content):
            from io import BytesIO
            import zipfile

            zip = zipfile.ZipFile(BytesIO(file_content))
            return zip.namelist()

        async def process_rar(file_content):
            from io import BytesIO
            import rarfile

            rar = rarfile.RarFile(BytesIO(file_content))
            output = []
            for f in rar.infolist():
                output.append(f.filename)

            return output

        async def process_tar(file_content):
            from io import BytesIO
            import tarfile

            tar = tarfile.open(fileobj=BytesIO(file_content))

            output = []
            for f in tar.getmembers():
                output.append(f.name)

            return output

        async def process_exe(file_content):
            return "user submitted an executable file. use a tool call that searches the web to fetch further information."

        ####################
        # start main url Processing
        #####
        output = {}

        # parse the URL
        url_parser = urllib.parse.urlparse(url)

        domain = url_parser.netloc
        file_name = url_parser.path.split("/")[-1]
        file_name_split = file_name.split(".")
        file_type = file_name_split[-1].lower() if len(file_name_split) > 1 else ""

        await emit_status(__event_emitter__, "Checking known domains..", False)

        # first, process any special domains, such as youtube
        output = await process_domains(domain, url)
        if output:
            return output

        # then if that didn't do anything, switch to Processing based on file type
        import hashlib

        await emit_status(__event_emitter__, "Fetching content..", False)
        # get the content of whatever file is at the url
        file_content = await _request(url)

        await emit_status(__event_emitter__, "Checking file type..", False)

        filetype_map = {
            ("htm", "html", "xhtml", "php", "asp"): process_webpage,
            (
                "asm",
                "bas",
                "bat",
                "c",
                "cc",
                "cfg",
                "cgi",
                "clj",
                "conf",
                "cpp",
                "css",
                "dart",
                "diff",
                "elm",
                "erl",
                "ex",
                "fs",
                "go",
                "hs",
                "ini",
                "java",
                "jl",
                "js",
                "json",
                "kt",
                "lisp",
                "log",
                "lua",
                "m",
                "md",
                "ml",
                "php",
                "pl",
                "ps1",
                "psm1",
                "patch",
                "py",
                "r",
                "rb",
                "rs",
                "s1",
                "scala",
                "scm",
                "sh",
                "sql",
                "swift",
                "ts",
                "txt",
                "toml",
                "tsx",
                "vim",
                "zsh",
            ): process_text,
            (
                "jpg",
                "jpeg",
                "png",
                "gif",
                "bmp",
                "svg",
                "tiff",
                "webp",
                "ico",
                "raw",
                "heic",
                "eps",
                "ai",
            ): process_image,
            ("mp3", "m4a", "ogg", "flac", "wma", "aiff", "wav", "aac"): process_audio,
            (
                "mp4",
                "mkv",
                "mov",
                "avi",
                "wmv",
                "mpeg",
                "mpg",
                "m4v",
            ): process_video,
            ("tar", "gz", "tgz"): process_tar,
            (
                "bin",
                "exe",
                "dll",
                "elf",
                "msi",
                "com",
                "cmd",
                "msp",
                "so",
                "a",
                "la",
                "bin",
                "dmg",
                "app",
                "appimage",
                "flatpak",
                "x64",
                "x86",
                "arm",
                "jar",
                "apk",
                "deb",
                "rpm",
            ): process_exe,
            ("zip",): process_zip,
            ("rar",): process_rar,
            ("xml",): process_xml,
            ("yaml",): process_yaml,
            ("csv",): process_csv,
            ("pdf",): process_pdf,
        }

        processor = None
        for exts, fetched_processor in filetype_map.items():
            if file_type in exts:
                processor = fetched_processor
                break

        if processor:
            await emit_status(
                __event_emitter__, f"Processing {file_type} file..", False
            )
            output = await processor(file_content)
            await emit_status(__event_emitter__, f"Processed {file_type} file", True)
        elif len(file_name_split) <= 1:
            # for now, we assume it's a website.
            # TODO: add mime type checking
            await emit_status(__event_emitter__, "Processing website..", False)
            output = await process_webpage(file_content)

            file_type = "website"
        else:
            # some unknown file format
            # add MIME type-based Processing later
            output = (
                "unsupported file format! you have to use another tool to process this."
            )
            await emit_message(__event_emitter__, "unsupported file format!")

        return {
            "url": url,
            "filename": file_name_split[0],
            "type": file_type,
            "size": len(file_content),
            "checksum": hashlib.sha256(file_content).hexdigest(),
            "data": output,
        }

    async def process_multiple_urls(
        self, urls: list, __user__: dict, __event_emitter__=None
    ) -> str:
        """
        processes multiple url's in sequence. can process the exact same data types as process_url.
        use this instead of process_url if user provided multiple url's!
        """

        output = []

        # limit to 4 threads at once
        semaphore = asyncio.Semaphore(4)

        async def handle_one(url, i):
            async with semaphore:
                try:
                    # for if the AI adds the url as a dict for some reason. it often does that!
                    url = url["url"]
                except:
                    pass

                try:
                    result = await self.process_url(url, __user__, __event_emitter__)
                    await emit_message(__event_emitter__, f"Processed link {i}\n")
                    return result
                except Exception as e:
                    return [f"ERROR Processing URL {url}: {e}"]

        tasks = [handle_one(url, i) for i, url in enumerate(urls)]
        output = await asyncio.gather(*tasks)

        await emit_status(__event_emitter__, f"Processed all links", True)

        return {
            "results": output,
            "ai_instructions": self.valves.multiple_urls_description_prompt,
        }

    async def search_web(
        self, query: str, __user__: dict, __event_emitter__=None
    ) -> str:
        """
        search the web for a query. uses process_url internally to process the resulting page.
        """

        return await self.process_url(
            f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}", __user__
        )

    async def get_most_up_to_date_information(
        self, query: str, __user__: dict, __event_emitter__=None
    ) -> str:
        """
        get the most up to date information about something by searching the web.
        """
        return await self.search_web(query, __user__)
