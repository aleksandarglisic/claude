import { Routes, Route } from 'react-router-dom'
import ChatWindow from './components/ChatWindow/ChatWindow'
import AdminPanel from './components/AdminPanel/AdminPanel'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ChatWindow />} />
      <Route path="/admin/*" element={<AdminPanel />} />
    </Routes>
  )
}
