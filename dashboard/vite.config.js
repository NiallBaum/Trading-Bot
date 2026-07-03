import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// IMPORTANT: change 'YOUR_REPO_NAME' below to your actual GitHub repo name.
// GitHub Pages serves project sites at https://username.github.io/repo-name/
// so Vite needs to know that sub-path to load assets correctly.
export default defineConfig({
  plugins: [react()],
  base: '/Trading-Bot/',
})
