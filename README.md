# Exam Studio

Exam Studio is a practice site for Data Analytics in Accounting. It includes 121 questions with worked solutions, a multi-turn tutor, and separate manipulation, interpretation and combined exams.

## Open the website

[Exam Studio on Cloudflare](https://exam-studio-preview.exam-studio-hosted.workers.dev/) opens without an account or password. For questions that need a dataset, the site names the file to open from your course materials.

## Build from source

The course datasets and generated question bank are rebuilt from an authorized local copy of the original course materials. Keep the same Excel and SQL folder names within that materials directory.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python build.py "/path/to/course/materials"
python -m unittest discover -s exam-studio-local -q
node --test exam-studio-local/test_formatting.cjs
```

Run `python exam-studio-local/server.py` and open [the local preview](http://127.0.0.1:8765/). Local tutor testing uses a Gemini API key entered in the browser form.

## Cloudflare preview

The hosted version uses Cloudflare Workers AI and a Durable Object per browser session for timed attempts. To deploy your own private instance, build first, then deploy from `exam-studio-hosted` using Wrangler with `PREVIEW_PASSWORD` supplied as a Worker secret. The app requires that secret before serving any content. The Basic Auth username for a private instance is `examstudio`. To deploy the password-free version, use `wrangler deploy --var PUBLIC_SITE:true`. In that mode, the Worker serves the app and points students to their course files. Dataset download routes stay private.

The public app scripts live in `exam-studio-preview`. The content builders, local server and tests live in `exam-studio-local`. The Worker and deployment configuration live in `exam-studio-hosted`.
