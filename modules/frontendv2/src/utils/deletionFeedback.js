const PENDING_FILE_CLEANUP_MESSAGE = 'A remoção dos arquivos está pendente e será tentada novamente.'

export function deletionFeedback(message, cleanupPending) {
  return cleanupPending ? `${message}. ${PENDING_FILE_CLEANUP_MESSAGE}` : message
}
