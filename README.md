# LiJ21 personal website

A responsive, build-free personal website for GitHub Pages. No dependencies or JavaScript required.

## Pages

- `index.html`: home and introduction
- `about.html`: personal biography placeholder
- `projects.html`: project collection, starting with this site
- `contact.html`: GitHub profile and space for more contact details
- `404.html`: missing-page fallback
- `assets/style.css`: shared layout, colors, and responsive styles

## Preview locally

From this directory, run:

```sh
python3 -m http.server 8000
```

Open http://localhost:8000. Stop the server with Ctrl+C.

## Personalize

Replace the LiJ21 display name and introductory text in each HTML page. Add your biography in `about.html`, real projects in `projects.html`, and contact links in `contact.html`. Update each page’s title and description as needed. The navigation and footer are plain HTML shared across pages; edit all pages when changing them. Colors and typography are defined in `assets/style.css`.

## Publish with GitHub Pages

Commit and push these files to the `main` branch of `LiJ21/LiJ21.github.io`. In the repository settings, configure Pages to deploy from the `main` branch and `/ (root)` directory. The expected address is https://LiJ21.github.io/ after GitHub finishes deployment. This setup has not been published by the local scaffold task.

The `.nojekyll` file keeps this a plain static site. No build step or package installation is needed.
