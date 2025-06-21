"""
title: URL Processor
author: Rose22
author_url: https://github.com/Rose22
requirements: bs4, xmltodict, pypdf, tinytag, moviepy, youtube-transcript-api, rarfile
version: 0.1.1
"""

from pydantic import BaseModel, Field
import os
import urllib
import hashlib
from bs4 import BeautifulSoup
from io import StringIO, BytesIO


class Tools:
    class Valves(BaseModel):
        user_agent: str = Field(
            default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
            description="the user agent to use for all web requests. the default should suffice!",
        )

    def __init__(self):
        self.valves = self.Valves()

        pass

    def _request(self, url):
        """
        INTERNAL FUNCTION, DO NOT USE!
        """
        # internal function, not for use by the llm

        try:
            conn = urllib.request.urlopen(
                urllib.request.Request(
                    url=url,
                    headers={"User-Agent": self.valves.user_agent},
                )
            )
        except urllib.request.URLError:
            raise Exception("Error: the URL was unreachable")
        except urllib.request.HTTPError as e:
            raise Exception(f"HTTP Error: {e.code} {e.reason}")

        return conn

    def process_url(self, url: str) -> str:
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
        - pdf's
        - documents
        - archive files such as zip and rar
        - youtube videos
        - executables
        """
        url_parser = urllib.parse.urlparse(url)

        domain = url_parser.netloc
        file_name = url_parser.path.split("/")[-1]
        file_name_split = file_name.split(".")
        file_ext = file_name_split[-1].lower()

        # get the content of whatever file is at the url
        file_content = self._request(url).read()

        output = False
        if "youtube" in domain or "youtu.be" in domain:
            # this is a youtube link. try and get the transcript!
            import youtube_transcript_api

            try:
                # get video transcript using a python module
                ytt_api = youtube_transcript_api.YouTubeTranscriptApi()

                # how to get the video id depends on if it's youtube or youtu.be
                if "youtube" in domain:
                    try:
                        # remove everything after the & sign first
                        video_id = url.split("&")[0]
                    except:
                        video_id = url

                    try:
                        # then get everything after ?v=
                        video_id = video_id.split("?v=")[1]
                    except Exception as e:
                        raise Exception(f"ERROR: malformed youtube URL! {e}")
                elif domain == "youtu.be":
                    try:
                        video_id = file_name.split("?")[0]
                    except IndexError:
                        video_id = file_name

                try:
                    transcript_obj = ytt_api.fetch(video_id)
                except:
                    # that likely means a transcript wasn't available in the preferred language.
                    # so fall back on the first one available:
                    try:
                        transcript_obj_list = list(ytt_api.list(video_id))
                        transcript_obj = transcript_obj_list[0].fetch()
                    except Exception as e:
                        return f"ERROR: error while fetching youtube transcript! {e}"

                transcript = []
                for snippet in transcript_obj:
                    transcript.append(snippet.text)
                transcript = " ".join(transcript)

                # get video title using beautifulsoup
                html = self._request(url).read()
                soup = BeautifulSoup(html, "html.parser")
                title = soup.find("title").get_text().strip()

                return {
                    "type": "youtube",
                    "title": title,
                    "transcript": {
                        "language": f"({transcript_obj.language_code}) {transcript_obj.language}",
                        "auto_generated": transcript_obj.is_generated,
                        "content": transcript,
                        "words": len(transcript.split(" ")),
                    },
                }
            except Exception as e:
                # many things can go wrong. i don't feel like catching each and every exception..
                # mostly, youtube transcript api needs to be kept up to date because youtube keeps changing.
                # and the pip version is far behind the git version.
                # you need the git version. and it's a bit of a hassle to install.
                # you basically need to get into openwebui's virtualenv and then manually git clone
                # the correct version instead of using pip.

                # so if it fails, just fall back on just processing it as a webpage.
                # at least we get the title that way!
                return f"ERROR: error while fetching youtube video data! {e}"

        if (
            file_ext in ("htm", "html", "xhtml", "php", "asp")
            or len(file_name_split) <= 1
        ):
            # it's a normal web page
            output = self._process_webpage(url)

            # make it look fancy to the llm
            file_ext = "website"
        elif file_ext in ("txt", "md", "json", "log", "ini", "conf", "cfg"):
            output = str(file_content)
        elif file_ext in (
            "sh",
            "bat",
            "py",
            "c",
            "cc",
            "cpp",
            "rs",
            "pl",
            "cgi",
            "js",
            "java",
            "go",
            "rb",
            "sql",
            "css",
        ):
            output = str(file_content)
        elif file_ext in ("jpg", "jpeg", "png", "gif"):
            import base64

            output = base64.b64encode(file_content).decode("utf-8")
        elif file_ext == "xml":
            import xmltodict

            output = xmltodict.parse(file_content)
        elif file_ext == "yaml":
            import yaml
            import json

            try:
                output = json.dumps(yaml.safe_load(file_content), indent=2)
            except yaml.YAMLError as e:
                return f"YAML Error: {e}"
        elif file_ext == "csv":
            import csv

            output = []
            for row in csv.reader(StringIO(str(file_content))):
                output.append(list(row))

        elif file_ext == "pdf":
            import pypdf

            pdf_reader = pypdf.PdfReader(BytesIO(file_content))
            pages_text = []
            for page in pdf_reader.pages:
                pages_text.append(page.extract_text())

            output = pages_text
        elif file_ext in ("mp3", "m4a", "ogg", "flac", "wma", "aiff", "wav"):
            import tinytag

            tag_reader = tinytag.TinyTag.get(file_obj=BytesIO(file_content))
            output = tag_reader.as_dict()
        elif file_ext in ("mp4", "mov", "avi"):
            import moviepy
            import tempfile

            # moviepy is stubborn and absolutely insists on a file name, not a file object
            # so let's write it to a file i guess...
            tmp_path = ""
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            clip = moviepy.VideoFileClip(tmp_path)
            os.remove(tmp_path)

            output = {
                "duration": clip.duration,
                "fps": clip.fps,
                "width": clip.w,
                "height": clip.h,
                "has_audio": clip.audio is not None,
                "audio_channels": clip.audio.nchannels if clip.audio else None,
                "audio_fps": clip.audio.fps if clip.audio else None,
                "misc": clip.reader.infos,
            }
        elif file_ext == "zip":
            import zipfile

            zip = zipfile.ZipFile(BytesIO(file_content))

            output = zip.namelist()
        elif file_ext == "rar":
            import rarfile

            rar = rarfile.RarFile(BytesIO(file_content))
            output = []
            for f in rar.infolist():
                output.append(f.filename)
        elif file_ext in ("tar", "gz"):
            import tarfile

            tar = tarfile.open(fileobj=BytesIO(file_content))

            output = []
            for f in tar.getmembers():
                output.append(f.name)
        elif file_ext in ("exe", "dll", "msi", "com", "cmd", "msp", "so", "a", "la"):
            return "user submitted an executable file. use a tool call that searches the web to fetch further information."
        else:
            # some unknown file format
            output = (
                "unsupported file format! you have to use another tool to process this."
            )

        return {
            "filename": file_name_split[0],
            "type": file_ext,
            "size": len(file_content),
            "checksum": hashlib.sha256(file_content).hexdigest(),
            "domain": domain,
            "data": output,
        }

    def process_multiple_urls(self, urls: list) -> str:
        """
        processes multiple url's in sequence.
        use this if user provided multiple url's.
        """
        output = []
        for url in urls:
            output.append(self.process_url(url))
        return output

    def _process_webpage(self, url):
        """
        INTERNAL FUNCTION, DO NOT USE!
        """
        # internal function, not for use by the llm

        # uses beautifulsoup to scrape a webpage

        import re

        html = self._request(url).read()
        soup = BeautifulSoup(html, "html.parser")

        output = {}

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

        # remove duplicates
        for category in output.keys():
            if category == "title":
                continue

            output[category] = list(set(output[category]))

        # but not always...
        if "headers" not in output.keys() and "paragraphs" not in output.keys():
            # if nothing was found, first, fall back on common CSS classes
            output["classes"] = {}
            for class_name in ("content", "description", "title", "text", "article"):
                output["classes"][class_name] = []
                for element in soup.find_all(class_=re.compile(rf"\b{class_name}\b")):
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
                output["classes"][class_name] = list(set(output["classes"][class_name]))

            if not output["classes"]:
                # still nothing?
                # then fall back on links if nothing could be extracted from the other html elements.
                # this is a last resort because it tends to be a lot of data to process

                del output["classes"]

                output["urls"] = []
                for a in soup.find_all("a", href=True):
                    output["urls"].append(a["href"])

                # remove duplicate links
                output["urls"] = list(set(output["urls"]))

                if not output["urls"]:
                    # alright, theres no saving this one. at least we have a title!
                    del output["urls"]

                    output["message"] = (
                        "nothing could be scraped from the page! use a web search tool call to find more information about this website."
                    )

        return output
