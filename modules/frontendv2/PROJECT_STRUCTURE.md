# 📁 Estrutura do Projeto - Frontend v2

```
frontendv2/
│
├── 📄 Configuration Files
│   ├── package.json              # Dependências e scripts
│   ├── vite.config.js           # Configuração do Vite
│   ├── tailwind.config.js       # Configuração do Tailwind CSS
│   ├── postcss.config.js        # Configuração do PostCSS
│   ├── .eslintrc.cjs            # Configuração do ESLint
│   ├── .env.example             # Exemplo de variáveis de ambiente
│   └── .gitignore               # Arquivos ignorados pelo Git
│
├── 🐳 Docker Files
│   ├── Dockerfile               # Build multi-stage do frontend
│   ├── docker-compose.yml       # Orquestração de containers
│   └── nginx.conf               # Configuração do Nginx
│
├── 📚 Documentation
│   ├── README.md                # Documentação principal
│   ├── SETUP.md                 # Guia de instalação
│   ├── COMMANDS.md              # Comandos úteis
│   └── PROJECT_STRUCTURE.md     # Este arquivo
│
├── 🌐 Public Assets
│   └── index.html               # HTML principal
│
└── 📂 src/                      # Código fonte
    │
    ├── 🎨 styles/
    │   └── index.css            # Estilos globais com Tailwind
    │
    ├── 🧩 components/           # Componentes reutilizáveis
    │   ├── Layout.jsx           # ⭐ Layout principal
    │   ├── Navbar.jsx           # ⭐ Barra de navegação superior
    │   ├── Sidebar.jsx          # ⭐ Menu lateral de navegação
    │   ├── Card.jsx             # Card genérico
    │   ├── Button.jsx           # Botão customizado
    │   ├── Loading.jsx          # Estados de carregamento
    │   └── EmptyState.jsx       # Estados vazios
    │
    ├── 📄 pages/                # Páginas da aplicação
    │   ├── Dashboard.jsx        # ⭐ Dashboard principal
    │   ├── NewTranscription.jsx # ⭐ Nova transcrição
    │   ├── Transcriptions.jsx   # ⭐ Lista de transcrições
    │   ├── TranscriptionDetail.jsx # ⭐ Detalhes da transcrição
    │   └── Settings.jsx         # ⭐ Configurações
    │
    ├── 🔌 services/             # Serviços e APIs
    │   ├── api.js               # Cliente Axios configurado
    │   └── audioService.js      # ⭐ Serviço de áudio/transcrição
    │
    ├── 🗄️ stores/               # Gerenciamento de estado (Zustand)
    │   ├── authStore.js         # ⭐ Estado de autenticação
    │   └── transcriptionStore.js # ⭐ Estado de transcrições
    │
    ├── 🪝 hooks/                # Custom React Hooks
    │   └── useAudio.js          # Hooks para operações de áudio
    │
    ├── 🛠️ utils/                # Utilitários
    │   ├── constants.js         # Constantes da aplicação
    │   └── helpers.js           # Funções auxiliares
    │
    ├── App.jsx                  # ⭐ App principal com roteamento
    └── main.jsx                 # ⭐ Entry point da aplicação
```

## 📊 Fluxo de Dados

```
┌─────────────────────────────────────────────────────────┐
│                    USUÁRIO INTERAGE                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    COMPONENTE (UI)                       │
│  Dashboard | NewTranscription | Transcriptions | etc.    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 HOOKS CUSTOMIZADOS                       │
│  useAudioUpload | useTranscriptions | useSystemHealth   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   SERVICES (API)                         │
│              audioService.js → api.js                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 BACKEND API (FastAPI)                    │
│              http://localhost:2020/...                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│            RESPOSTA ATUALIZA STORES                      │
│        authStore | transcriptionStore (Zustand)          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              COMPONENTE RE-RENDERIZA                     │
│                  (React Reactivity)                      │
└─────────────────────────────────────────────────────────┘
```

## 🎯 Hierarquia de Componentes

```
App.jsx
├── Router
    ├── Layout.jsx
    │   ├── Navbar.jsx              # Logo + Nome do usuário
    │   ├── Sidebar.jsx             # Menu de navegação
    │   └── Outlet (Rotas)
    │       ├── Dashboard.jsx       # Página inicial
    │       │   ├── Card
    │       │   ├── StatCard
    │       │   └── ModelStatusCard
    │       │
    │       ├── NewTranscription.jsx # Upload de arquivo
    │       │   ├── Card
    │       │   ├── Button
    │       │   └── Dropzone
    │       │
    │       ├── Transcriptions.jsx   # Lista
    │       │   ├── Card
    │       │   ├── Button
    │       │   └── EmptyState
    │       │
    │       ├── TranscriptionDetail.jsx # Detalhes
    │       │   ├── Card
    │       │   ├── Button
    │       │   └── StatCard
    │       │
    │       └── Settings.jsx         # Configurações
    │           ├── Card
    │           └── Button
    │
    └── Toaster (react-hot-toast)
```

## 🔄 Fluxo de Rotas

```
/                           → Dashboard.jsx
/new-transcription          → NewTranscription.jsx
/transcriptions             → Transcriptions.jsx
/transcriptions/:id         → TranscriptionDetail.jsx
/settings                   → Settings.jsx
/* (qualquer outra rota)    → Redirect para /
```

## 📦 Principais Dependências

### Core
- `react` + `react-dom` - Biblioteca UI
- `vite` - Build tool

### Roteamento
- `react-router-dom` - Gerenciamento de rotas

### Estado
- `zustand` - Gerenciamento de estado global

### HTTP
- `axios` - Cliente HTTP

### UI/UX
- `tailwindcss` - Framework CSS
- `lucide-react` - Ícones
- `react-hot-toast` - Notificações
- `framer-motion` - Animações

### Upload
- `react-dropzone` - Drag & drop de arquivos

### Utilitários
- `date-fns` - Manipulação de datas

## 🎨 Sistema de Design

### Cores Primárias (Tailwind)
```css
primary-50:  #f5f3ff
primary-100: #ede9fe
primary-200: #ddd6fe
primary-300: #c4b5fd
primary-400: #a78bfa
primary-500: #8b5cf6  ← Cor principal
primary-600: #7c3aed
primary-700: #6d28d9
primary-800: #5b21b6
primary-900: #4c1d95
```

### Componentes Base
- **Card**: Container branco com shadow
- **Button**: Variantes (primary, secondary, outline, danger, ghost)
- **Badge**: Tags coloridas por status
- **Input**: Input estilizado com focus ring

## 🔐 Autenticação (Placeholder)

```javascript
// authStore.js - Zustand Store
{
  user: {
    id: 1,
    name: 'Usuário Demo',
    email: 'demo@transcricao.ai',
    initials: 'UD',
    avatar: null
  },
  isAuthenticated: true
}
```

## 🌐 Endpoints da API

```javascript
GET    /health                    # Status do sistema
GET    /stats                     # Estatísticas gerais
POST   /transcriptions/jobs       # Upload e job assíncrono
GET    /transcriptions/jobs/:id/status # Polling do job
GET    /transcriptions            # Listar transcrições
GET    /transcriptions/:id        # Detalhes da transcrição
DELETE /transcriptions/:id        # Excluir transcrição
```

Os antigos endpoints síncronos de processamento foram removidos na P1-A. O
frontend não conhece qual implementação interna do Whisper é usada pelo worker.

## 🚀 Scripts Disponíveis

```json
{
  "dev": "vite",                 // Servidor de desenvolvimento
  "build": "vite build",         // Build de produção
  "preview": "vite preview",     // Preview do build
  "lint": "eslint . --ext js,jsx" // Linting
}
```

## 📱 Responsividade

### Breakpoints Tailwind
- `sm`: 640px   - Mobile landscape
- `md`: 768px   - Tablet
- `lg`: 1024px  - Desktop
- `xl`: 1280px  - Large desktop
- `2xl`: 1536px - Extra large

### Layout Responsivo
- Mobile: Sidebar colapsada, stack vertical
- Tablet: Sidebar visível, layout flex
- Desktop: Layout completo com sidebar fixa

## 🎯 Features por Página

### Dashboard (/)
✅ Status dos modelos
✅ Estatísticas do sistema
✅ Transcrições recentes
✅ Links rápidos

### Nova Transcrição (/new-transcription)
✅ Upload com drag & drop
✅ Seleção de modelo
✅ Toggle de diarização
✅ Barra de progresso

### Transcrições (/transcriptions)
✅ Lista paginada
✅ Busca por nome
✅ Filtro por status
✅ Ações (ver, excluir)

### Detalhes (/transcriptions/:id)
✅ Visualização completa
✅ Segmentos por falante
✅ Estatísticas detalhadas
✅ Download (TXT, JSON, SRT)
✅ Copiar para clipboard

### Configurações (/settings)
✅ Perfil do usuário
✅ Status do sistema
✅ Informações dos modelos

## 🔮 Próximos Passos

- [ ] Autenticação JWT
- [ ] WebSocket para atualizações em tempo real
- [ ] Editor de transcrições
- [ ] Tema escuro
- [ ] Testes unitários
- [ ] PWA
- [ ] Internacionalização (i18n)
