"""
Serviço de geração de atas de reunião usando IA (Gemini).
"""

import logging
import time
import google.generativeai as genai
from typing import Dict, List, Optional
from ..config import settings

logger = logging.getLogger(__name__)


class MeetingMinutesGenerator:
    """Gera atas de reunião a partir de transcrições usando IA."""
    
    def __init__(self, api_key: str):
        """
        Inicializa o gerador de atas.
        
        Args:
            api_key: Chave da API do Google Gemini
        """
        self.api_key = api_key
        self._configure()
    
    def _configure(self):
        """Configura o cliente Gemini."""
        try:
            genai.configure(api_key=self.api_key)
            # Use the deployment's configured model for both supported flows.
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
            logger.info("✅ Gemini configurado para geração de atas")
        except Exception as e:
            logger.error("Unable to configure Gemini (%s)", type(e).__name__)
            raise

    def generate_intelligence(self, prompt: str) -> str:
        """Reuse the Gemini client; domain validation occurs in the Worker."""
        started = time.monotonic()
        response = self.model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.1, "max_output_tokens": 16384},
            request_options={"timeout": min(settings.MEETING_MINUTES_TIMEOUT_SECONDS, 300), "retry": None},
        )
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini intelligence metrics model=%s latency_seconds=%.3f input_tokens=%s output_tokens=%s total_tokens=%s retries=0",
            settings.GEMINI_MODEL, time.monotonic() - started,
            getattr(usage, "prompt_token_count", None), getattr(usage, "candidates_token_count", None),
            getattr(usage, "total_token_count", None),
        )
        if not response.text:
            raise ValueError("Empty Gemini response")
        return response.text
    
    def generate_minutes(
        self,
        transcription: str,
        meeting_context: Optional[Dict] = None
    ) -> Dict:
        """
        Gera ata de reunião a partir da transcrição.
        
        Args:
            transcription: Texto transcrito da reunião
            meeting_context: Contexto adicional (título, participantes, data, etc.)
            
        Returns:
            Dicionário com a ata estruturada
        """
        try:
            # Preparar contexto
            context_info = ""
            if meeting_context:
                if meeting_context.get("title"):
                    context_info += f"\n**Título da Reunião**: {meeting_context['title']}"
                if meeting_context.get("date"):
                    context_info += f"\n**Data**: {meeting_context['date']}"
                if meeting_context.get("participants"):
                    participants = ", ".join(meeting_context['participants'])
                    context_info += f"\n**Participantes**: {participants}"
            
            # Criar prompt estruturado
            prompt = f"""Você é um assistente especializado em criar atas de reunião profissionais.

{context_info}

**TRANSCRIÇÃO DA REUNIÃO**:
{transcription}

---

Por favor, analise a transcrição acima e gere uma ata de reunião completa e estruturada em português seguindo este formato EXATO:

## 📋 RESUMO EXECUTIVO
[Escreva um parágrafo resumindo os principais pontos da reunião - máximo 3-4 linhas]

## 🎯 OBJETIVOS DA REUNIÃO
- [Liste os objetivos discutidos]
- [Cada objetivo em um bullet point]

## 💡 PRINCIPAIS TÓPICOS DISCUTIDOS
### Tópico 1: [Nome do tópico]
- [Detalhe importante 1]
- [Detalhe importante 2]

### Tópico 2: [Nome do tópico]
- [Detalhe importante 1]
- [Detalhe importante 2]

[Repita para cada tópico relevante]

## ✅ DECISÕES TOMADAS
1. [Decisão 1 - seja específico]
2. [Decisão 2 - seja específico]
3. [Continue numerando as decisões]

## 📝 TO-DO LIST / AÇÕES
- [ ] **[Responsável]**: [Descrição da tarefa] - Prazo: [se mencionado]
- [ ] **[Responsável]**: [Descrição da tarefa] - Prazo: [se mencionado]

## 🔄 PRÓXIMOS PASSOS
- [Próximo passo 1]
- [Próximo passo 2]

## 📌 OBSERVAÇÕES E NOTAS
- [Qualquer observação relevante]
- [Pontos que requerem atenção]

---

**INSTRUÇÕES IMPORTANTES**:
1. Use APENAS informações presentes na transcrição
2. Se não houver informação para alguma seção, escreva "Não especificado na reunião"
3. Seja conciso mas completo
4. Use linguagem profissional
5. Identifique responsáveis quando mencionados
6. Se houver prazos mencionados, inclua-os
7. Mantenha a ordem cronológica dos tópicos quando possível
"""

            # Gerar ata
            logger.info("🤖 Gerando ata de reunião com Gemini...")
            response = self.model.generate_content(prompt)
            
            if not response.text:
                raise ValueError("Gemini retornou resposta vazia")
            
            ata_text = response.text.strip()
            
            # Extrair to-do list estruturada
            todo_items = self._extract_todo_items(ata_text)
            
            # Extrair decisões
            decisions = self._extract_decisions(ata_text)
            
            logger.info("✅ Ata de reunião gerada com sucesso")
            
            return {
                "full_text": ata_text,
                "summary": self._extract_section(ata_text, "RESUMO EXECUTIVO"),
                "objectives": self._extract_list(ata_text, "OBJETIVOS DA REUNIÃO"),
                "topics": self._extract_list(ata_text, "PRINCIPAIS TÓPICOS DISCUTIDOS"),
                "decisions": decisions,
                "todo_list": todo_items,
                "next_steps": self._extract_list(ata_text, "PRÓXIMOS PASSOS"),
                "notes": self._extract_section(ata_text, "OBSERVAÇÕES E NOTAS"),
            }
        
        except Exception as e:
            logger.error("Unable to generate meeting minutes (%s)", type(e).__name__)
            raise
    
    def _extract_section(self, text: str, section_title: str) -> str:
        """Extrai uma seção específica da ata como texto."""
        try:
            # Procurar pelo título da seção
            lines = text.split("\n")
            in_section = False
            section_lines = []
            
            for line in lines:
                # Detectar início da seção
                if section_title in line.upper():
                    in_section = True
                    continue
                
                # Detectar fim da seção (próximo ##)
                if in_section and line.startswith("##"):
                    break
                
                # Coletar linhas da seção
                if in_section:
                    section_lines.append(line)
            
            return "\n".join(section_lines).strip()
        
        except Exception:
            return ""
    
    def _extract_list(self, text: str, section_title: str) -> List[str]:
        """Extrai uma seção específica da ata como lista."""
        try:
            section_text = self._extract_section(text, section_title)
            if not section_text:
                return []
            
            items = []
            lines = section_text.split("\n")
            
            for line in lines:
                line = line.strip()
                # Remover marcadores de lista
                if line.startswith("-"):
                    clean_line = line.lstrip("- ").strip()
                    if clean_line and not clean_line.startswith("#"):
                        items.append(clean_line)
                elif line and not line.startswith("#"):
                    # Linhas sem marcador mas com conteúdo
                    items.append(line)
            
            return items
        
        except Exception:
            return []
    
    def _extract_todo_items(self, text: str) -> List[Dict]:
        """Extrai itens de to-do list estruturados."""
        try:
            todo_section = self._extract_section(text, "TO-DO LIST")
            if not todo_section:
                return []
            
            items = []
            lines = todo_section.split("\n")
            
            for line in lines:
                line = line.strip()
                if line.startswith("- [ ]") or line.startswith("-"):
                    # Tentar extrair responsável e descrição
                    text_content = line.replace("- [ ]", "").replace("-", "").strip()
                    
                    # Padrão: **[Responsável]**: [Descrição] - Prazo: [data]
                    responsible = "Não atribuído"
                    description = text_content
                    deadline = None
                    
                    if "**" in text_content:
                        parts = text_content.split("**")
                        if len(parts) >= 3:
                            responsible = parts[1].strip()
                            description = parts[2].replace(":", "").strip()
                    
                    if "Prazo:" in description:
                        desc_parts = description.split("Prazo:")
                        description = desc_parts[0].strip()
                        deadline = desc_parts[1].strip()
                    
                    items.append({
                        "task": description,
                        "responsible": responsible,
                        "deadline": deadline
                    })
            
            return items
        
        except Exception:
            return []
    
    def _extract_decisions(self, text: str) -> List[Dict]:
        """Extrai lista de decisões."""
        try:
            decisions_section = self._extract_section(text, "DECISÕES TOMADAS")
            if not decisions_section:
                return []
            
            decisions = []
            lines = decisions_section.split("\n")
            
            for line in lines:
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("-")):
                    # Remover numeração ou bullet
                    clean_line = line.lstrip("0123456789.-) ").strip()
                    if clean_line:
                        # Tentar extrair responsável se mencionado
                        responsible = None
                        decision_text = clean_line
                        
                        # Padrão: texto (Responsável: Nome) ou - Responsável: Nome
                        if "Responsável:" in clean_line:
                            parts = clean_line.split("Responsável:")
                            decision_text = parts[0].strip()
                            responsible = parts[1].strip().rstrip(")")
                        
                        decisions.append({
                            "decision": decision_text,
                            "responsible": responsible
                        })
            
            return decisions
        
        except Exception:
            return []
    
    def get_config_status(self) -> Dict:
        """Retorna status da configuração."""
        return {
            "configured": bool(self.api_key),
            "model": settings.GEMINI_MODEL
        }
