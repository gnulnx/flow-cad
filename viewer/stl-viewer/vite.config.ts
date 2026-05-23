import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { createReadStream, existsSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const viewerRoot = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(viewerRoot, '../..')
const stlRoot = path.join(repoRoot, 'b3/exports/stl')

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'flow-cad-stl-exports',
      configureServer(server) {
        server.middlewares.use('/exports/stl', (req, res, next) => {
          const pathname = new URL(req.url ?? '', 'http://localhost').pathname
          const requestedPath = path.normalize(path.join(stlRoot, decodeURIComponent(pathname)))

          if (!requestedPath.startsWith(stlRoot) || !existsSync(requestedPath) || !statSync(requestedPath).isFile()) {
            next()
            return
          }

          res.setHeader('Content-Type', 'model/stl')
          createReadStream(requestedPath).pipe(res)
        })
      },
    },
  ],
  server: {
    port: 3000,
    open: true,
  },
})
