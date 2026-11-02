# SAMI DEVELOPER V6 — Portfolio & CMS

A standalone, responsive Arabic/English portfolio with a private admin dashboard. No n8n service or external API keys required.

## Included
- Responsive bilingual landing page with project cards, contact form, visual effects and accessible reduced-motion fallback.
- Secure admin login with session cookies, CSRF checks, project create/edit/delete, featured projects.
- Upload images **from your computer** (JPG/PNG/WebP up to 5 MB), automatic WebP conversion, persistent image storage, image replacement/removal. No image URLs required.
- Editable site content (hero, about, email and social links) from the admin dashboard.
- Contact inbox with delete action.
- SQLite data persistence in `/data/site.db` and uploads in `/data/uploads`.

## Deploy on Coolify
1. Create a NEW private GitHub repository `sami-developer-v6`. Unzip and upload all files at the repo root, including `docker-compose.yml`.
2. Coolify > New Project > New Resource > Private Repository (GitHub App) > Docker Compose. Branch `main`, Compose file `/docker-compose.yml`.
3. Add environment variables `ADMIN_USER`, `ADMIN_PASSWORD`, `APP_SECRET` (long random secret), `HTTPS_ONLY=true`. Never commit real passwords.
4. Configure service `web`, HTTPS, domain (use a preview subdomain first), port `8000`, then Deploy.
5. Visit `/admin/login`, sign in, test upload and editing, then connect the main domain.
6. Keep the named volume `sami-v6-data` when redeploying. Deleting it destroys the database and uploaded images.

## Local run
Copy `.env.example` to `.env`, replace all placeholders, then `docker compose up --build -d`. For local HTTP testing set `HTTPS_ONLY=false`. The Compose service is exposed internally on 8000 and needs a reverse proxy (Coolify supplies this in production).

## Notes
- The app stores images locally and does not require an image URL.
- First startup seeds three example projects; edit/delete them in Admin.
- Admin actions require authentication and a CSRF token.
- For public internet exposure, put the app behind HTTPS, configure backups, and consider rate limiting for contact/login.
- Browser layouts target current Chrome, Firefox, Edge, and Safari. Automated cross-browser testing has not been performed.
- Don't copy a V5 database into V6 without reviewing the schema and making a backup.
