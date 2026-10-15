# AssemblyAI: execução e limites operacionais

## Modelo e credenciais

A chave de plataforma é exclusiva para uso USAGI. Ela fica somente no Worker;
a API recebe apenas `AAI_API_KEY_CONFIGURED` como indicador. A presença da
chave, isoladamente, nunca autoriza chamadas. A beta usa `Universal-3.5 Pro`
com `speaker_labels` habilitado e sem lista de fallback. BYOK permanece separado:
usa a credencial do próprio usuário, não consome a franquia da USAGI nem o
orçamento de plataforma e não muda automaticamente para a chave da plataforma
quando falha. O default geral de transcrição continua `whisper`; selecionar
AssemblyAI é explícito.

O SDK fixa `speech_models` para evitar que um alias legado altere o modelo no
provider. A API não importa o SDK. Para o ciclo de concessões, revisão de saldo,
limites, reconciliação e suspensão, consulte o [runbook da beta fechada](closed_beta.md).

## Ledger e estimação

O orçamento cumulativo e as chamadas são registrados no banco e serializados
entre workers. A reserva usa a tarifa configurada e a duração validada, é
arredondada para cima e impede novas submissões quando ultrapassa o menor teto
aplicável. Isso é autorização interna conservadora, não fatura, captura de saldo
do provider nem garantia de que a conta externa não cobrará além do teto.

Na admissão, antes de conhecer a duração decodificada, a reserva inicial usa o
limite máximo permitido para o arquivo. Depois da decodificação no Worker e
antes do POST ao provider, ela é redimensionada proporcionalmente à duração
validada. Assim, a pré-reserva protege a admissão e não representa duração ou
custo efetivamente processado.

O preço público consultado para o modelo pré-gravado é US$0,21/h para
Universal-3.5 Pro e US$0,02/h para speaker diarization, total de referência de
US$0,23/h com falantes. O preço pode mudar e condições contratuais podem diferir;
revise a fonte oficial antes de configurar a versão de preço. O exemplo de
planejamento na [beta fechada](closed_beta.md) é estimativa, não gasto observado.

Confirmação operacional registra a tarifa explicitamente configurada em
`UsagePrice` para a versão informada; estimativas derivadas do ledger não são
faturas. Uma mudança de modelo, tarifa ou versão exige drenar a fila e seguir o
procedimento de nova revisão. A migration `20261015_0017` preserva histórico e
seu downgrade recusa remover evidência financeira protegida.

## Retenção e estado

Exclusão e TTL da USAGI controlam somente o armazenamento local. Não executam
DELETE remoto nem configuram retenção ou treinamento na AssemblyAI. Configure
retenção, opt-out, consentimento e procedimento de remoção remota de acordo com
o contrato do provider antes de oferecer serviço público. A implementação desta
entrega ainda não foi homologada para produção nem para uso pago do provider.

Fonte primária de preços: [AssemblyAI Pricing](https://www.assemblyai.com/pricing).

## Evidência histórica

Em 2 de outubro de 2026, dois smokes antigos usaram Universal-2 na conta
`usagip4auth`. O ledger registrou 34 centavos em autorizações/reservas, não uma
fatura ou confirmação de gasto cobrado. Essa evidência não valida Universal-3.5
Pro nem homologa esta entrega. Não foram feitas chamadas novas nesta atualização;
qualquer teste futuro com provider requer autorização operacional própria.
