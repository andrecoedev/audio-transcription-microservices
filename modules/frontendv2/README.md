# Transcritor AI - Frontend v2

Frontend moderno para o sistema de transcrição de áudio usando React + Vite.

## 🚀 Tecnologias

- **React 18** - Biblioteca UI
- **Vite** - Build tool super rápido
- **React Router** - Roteamento
- **Tailwind CSS** - Estilização
- **Zustand** - Gerenciamento de estado
- **Axios** - Cliente HTTP
- **Lucide React** - Ícones
- **React Hot Toast** - Notificações
- **React Dropzone** - Upload de arquivos
- **Framer Motion** - Animações

## 📋 Pré-requisitos

- Node.js 18+ 
- NPM ou Yarn
- Backend rodando na porta 2020

## 🛠️ Instalação

```bash
# Instalar dependências
npm install

# Ou com yarn
yarn install
```

## ⚙️ Configuração

Crie um arquivo `.env` na raiz:

```env
VITE_API_URL=http://localhost:2020
```

## 🚀 Execução

### Modo Desenvolvimento
```bash
npm run dev
# Acesse: http://localhost:3000
```

### Build de Produção
```bash
npm run build
npm run preview
```

## 🐳 Docker

```bash
# Build da imagem
docker build -t transcricao-frontend-v2 .

# Executar container
docker run -p 3000:3000 transcricao-frontend-v2
```

## 📁 Estrutura do Projeto

```
src/
├── components/        # Componentes reutilizáveis
│   ├── Layout.jsx    # Layout principal
│   ├── Navbar.jsx    # Barra de navegação
│   ├── Sidebar.jsx   # Menu lateral
│   ├── Card.jsx      # Componente de card
│   └── Button.jsx    # Botão customizado
├── pages/            # Páginas da aplicação
│   ├── Dashboard.jsx           # Dashboard principal
│   ├── NewTranscription.jsx    # Nova transcrição
│   ├── Transcriptions.jsx      # Lista de transcrições
│   ├── TranscriptionDetail.jsx # Detalhes da transcrição
│   └── Settings.jsx            # Configurações
├── services/         # Serviços e APIs
│   ├── api.js               # Cliente Axios configurado
│   └── audioService.js      # Serviço de áudio/transcrição
├── stores/           # Gerenciamento de estado (Zustand)
│   ├── authStore.js         # Estado de autenticação
│   └── transcriptionStore.js # Estado de transcrições
├── styles/           # Estilos globais
│   └── index.css     # CSS com Tailwind
├── App.jsx           # App principal com rotas
└── main.jsx          # Entry point
```

## 🎨 Funcionalidades

### ✅ Implementadas

- **Dashboard**
  - Visão geral do sistema
  - Status dos modelos (Whisper, AssemblyAI, Pyannote)
  - Estatísticas de transcrições
  - Transcrições recentes

- **Nova Transcrição**
  - Upload de arquivos com drag & drop
  - Seleção de modelo (Whisper/AssemblyAI)
  - Opção de diarização de falantes
  - Barra de progresso de upload

- **Lista de Transcrições**
  - Listagem completa
  - Busca por nome
  - Filtro por status
  - Ações (visualizar, excluir)

- **Detalhes da Transcrição**
  - Visualização completa
  - Segmentos por falante
  - Estatísticas detalhadas
  - Download em múltiplos formatos (TXT, JSON, SRT)
  - Copiar para área de transferência

- **Configurações**
  - Perfil do usuário
  - Status do sistema
  - Informações dos modelos

### 🎯 Componentes Reutilizáveis

- **Layout**: Estrutura principal com Navbar + Sidebar
- **Navbar**: Logo + Info do usuário
- **Sidebar**: Navegação principal e secundária
- **Card**: Container estilizado
- **Button**: Botão com variantes e estados

### 🔄 Integrações Backend

#### Endpoints Utilizados:
- `GET /health` - Status do sistema
- `GET /stats` - Estatísticas gerais
- `POST /transcriptions/jobs` - Upload e criação do job assíncrono
- `GET /transcriptions/jobs/:id/status` - Polling do job
- `GET /transcriptions` - Listar transcrições
- `GET /transcriptions/:id` - Detalhes da transcrição
- `DELETE /transcriptions/:id` - Excluir transcrição

## 🎨 Design System

### Cores Principais
- **Primary**: Purple (#8b5cf6)
- **Success**: Green (#10b981)
- **Warning**: Yellow (#f59e0b)
- **Error**: Red (#ef4444)

### Componentes Tailwind Customizados
- `.card` - Cards com shadow e border
- `.btn-primary` - Botão primário
- `.btn-secondary` - Botão secundário
- `.badge` - Badge com variantes
- `.input` - Input estilizado

## 📱 Responsividade

O frontend é totalmente responsivo e funciona em:
- 📱 Mobile (320px+)
- 📱 Tablet (768px+)
- 💻 Desktop (1024px+)
- 🖥️ Large Desktop (1280px+)

## 🔒 Autenticação

Atualmente usa um usuário demo. Para implementar autenticação real:

1. Atualizar `authStore.js` com lógica de login
2. Adicionar rotas protegidas
3. Implementar refresh token
4. Conectar com backend de autenticação

## 🚀 Deploy

### Vercel
```bash
npm install -g vercel
vercel
```

### Netlify
```bash
npm run build
# Fazer upload da pasta dist/
```

### Docker + Nginx
```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT.

## 👥 Autor

Desenvolvido com ❤️ para o projeto Transcritor AI

## 🐛 Problemas Conhecidos

- [ ] Melhorar tratamento de erros em uploads grandes
- [ ] Adicionar testes unitários
- [ ] Implementar sistema de notificações em tempo real
- [ ] Adicionar suporte a temas (claro/escuro)

## 🔮 Roadmap

- [ ] Autenticação JWT completa
- [ ] WebSocket para atualizações em tempo real
- [ ] Editor de transcrições
- [ ] Exportação em mais formatos (DOCX, PDF)
- [ ] Modo offline com IndexedDB
- [ ] PWA (Progressive Web App)
- [ ] Analytics e métricas
- [ ] Compartilhamento de transcrições
- [ ] Colaboração em tempo real
