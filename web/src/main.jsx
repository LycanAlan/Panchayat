import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'

import './styles/reset.css'
import './styles/tokens.css'
import './styles/type.css'
import './styles/layout.css'
import './styles/paper.css'
import './styles/plan.css'
import './styles/components.css'
import './styles/pages.css'

// Every route opens on a plate or a file header; a browser-restored
// scroll position drops the reader into the middle of a pinned
// sequence whose triggers have not measured yet.
if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual'
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
