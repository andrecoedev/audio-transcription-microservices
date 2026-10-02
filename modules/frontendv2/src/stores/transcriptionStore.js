import { create } from 'zustand'

export const useTranscriptionStore = create((set) => ({
  transcriptions: [],
  currentTranscription: null,
  isLoading: false,
  error: null,
  stats: {
    total: 0,
    completed: 0,
    processing: 0,
    failed: 0,
  },

  setTranscriptions: (transcriptions) => set({ transcriptions }),
  setCurrentTranscription: (transcription) => set({ currentTranscription: transcription }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  setStats: (stats) => set({ stats }),
  
  addTranscription: (transcription) => set((state) => ({
    transcriptions: [transcription, ...state.transcriptions]
  })),
  
  updateTranscription: (id, updates) => set((state) => ({
    transcriptions: state.transcriptions.map(t => 
      t.id === id ? { ...t, ...updates } : t
    ),
    currentTranscription: state.currentTranscription?.id === id 
      ? { ...state.currentTranscription, ...updates }
      : state.currentTranscription
  })),
  
  removeTranscription: (id) => set((state) => ({
    transcriptions: state.transcriptions.filter(t => t.id !== id)
  })),
}))
