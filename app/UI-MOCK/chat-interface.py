# import React, { useState, useEffect, useRef } from 'react';
# import { Send, Plus, Trash2, Loader2 } from 'lucide-react';

# export default function ChatInterface() {
#   const [conversations, setConversations] = useState([]);
#   const [activeConversation, setActiveConversation] = useState(null);
#   const [messages, setMessages] = useState([]);
#   const [input, setInput] = useState('');
#   const [loading, setLoading] = useState(false);
#   const messagesEndRef = useRef(null);
#   const API_BASE = 'http://localhost:8000/api';

#   useEffect(() => {
#     messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
#   }, [messages]);

#   useEffect(() => {
#     fetchConversations();
#   }, []);

#   const fetchConversations = async () => {
#     try {
#       const res = await fetch(`${API_BASE}/conversations`, {
#         headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
#       });
#       const data = await res.json();
#       setConversations(data);
#     } catch (err) {
#       console.error('Failed to load conversations:', err);
#     }
#   };

#   const loadConversation = async (convId) => {
#     try {
#       setActiveConversation(convId);
#       const res = await fetch(`${API_BASE}/conversations/${convId}/messages`, {
#         headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
#       });
#       const data = await res.json();
#       setMessages(data);
#     } catch (err) {
#       console.error('Failed to load messages:', err);
#     }
#   };

#   const createNewConversation = async () => {
#     try {
#       const res = await fetch(`${API_BASE}/conversations`, {
#         method: 'POST',
#         headers: {
#           'Authorization': `Bearer ${localStorage.getItem('token')}`,
#           'Content-Type': 'application/json'
#         },
#         body: JSON.stringify({ title: 'New Chat' })
#       });
#       const newConv = await res.json();
#       setConversations([newConv, ...conversations]);
#       setActiveConversation(newConv.conversation_id);
#       setMessages([]);
#     } catch (err) {
#       console.error('Failed to create conversation:', err);
#     }
#   };

#   const deleteConversation = async (convId, e) => {
#     e.stopPropagation();
#     try {
#       await fetch(`${API_BASE}/conversations/${convId}`, {
#         method: 'DELETE',
#         headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
#       });
#       setConversations(conversations.filter(c => c.conversation_id !== convId));
#       if (activeConversation === convId) {
#         setActiveConversation(null);
#         setMessages([]);
#       }
#     } catch (err) {
#       console.error('Failed to delete conversation:', err);
#     }
#   };

#   const sendMessage = async () => {
#     if (!input.trim() || !activeConversation || loading) return;

#     const userMessage = { role: 'user', content: input, created_at: new Date().toISOString() };
#     setMessages([...messages, userMessage]);
#     const currentInput = input;
#     setInput('');
#     setLoading(true);

#     try {
#       const res = await fetch(`${API_BASE}/conversations/${activeConversation}/messages`, {
#         method: 'POST',
#         headers: {
#           'Authorization': `Bearer ${localStorage.getItem('token')}`,
#           'Content-Type': 'application/json'
#         },
#         body: JSON.stringify({ content: currentInput })
#       });
#       const assistantMessage = await res.json();
#       setMessages(prev => [...prev, assistantMessage]);
#     } catch (err) {
#       console.error('Failed to send message:', err);
#       setMessages(prev => [...prev, {
#         role: 'assistant',
#         content: 'Sorry, something went wrong. Please try again.',
#         created_at: new Date().toISOString()
#       }]);
#     } finally {
#       setLoading(false);
#     }
#   };

#   const handleKeyPress = (e) => {
#     if (e.key === 'Enter' && !e.shiftKey) {
#       e.preventDefault();
#       sendMessage();
#     }
#   };

#   return (
#     <div className="flex h-screen bg-gray-50">
#       {/* Sidebar */}
#       <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
#         <div className="p-4 border-b border-gray-200">
#           <button
#             onClick={createNewConversation}
#             className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
#           >
#             <Plus size={18} />
#             New Chat
#           </button>
#         </div>

#         <div className="flex-1 overflow-y-auto">
#           {conversations.map(conv => (
#             <div
#               key={conv.conversation_id}
#               onClick={() => loadConversation(conv.conversation_id)}
#               className={`px-4 py-3 cursor-pointer hover:bg-gray-100 border-b border-gray-100 transition group ${
#                 activeConversation === conv.conversation_id ? 'bg-blue-50' : ''
#               }`}
#             >
#               <div className="flex items-center justify-between">
#                 <div className="flex-1 min-w-0">
#                   <p className="text-sm font-medium text-gray-900 truncate">
#                     {conv.title}
#                   </p>
#                   <p className="text-xs text-gray-500">
#                     {conv.message_count} messages
#                   </p>
#                 </div>
#                 <button
#                   onClick={(e) => deleteConversation(conv.conversation_id, e)}
#                   className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 rounded transition"
#                 >
#                   <Trash2 size={14} className="text-red-600" />
#                 </button>
#               </div>
#             </div>
#           ))}
#         </div>
#       </div>

#       {/* Main Chat Area */}
#       <div className="flex-1 flex flex-col">
#         {activeConversation ? (
#           <>
#             {/* Messages */}
#             <div className="flex-1 overflow-y-auto p-6 space-y-6">
#               {messages.map((msg, idx) => (
#                 <div
#                   key={idx}
#                   className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
#                 >
#                   <div
#                     className={`max-w-3xl ${
#                       msg.role === 'user'
#                         ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm'
#                         : 'bg-white border border-gray-200 rounded-2xl rounded-tl-sm'
#                     } px-5 py-3 shadow-sm`}
#                   >
#                     <p className={`text-sm whitespace-pre-wrap ${
#                       msg.role === 'user' ? 'text-white' : 'text-gray-800'
#                     }`}>
#                       {msg.content}
#                     </p>
#                     {msg.sources && (
#                       <div className="mt-2 pt-2 border-t border-gray-200">
#                         <p className="text-xs text-gray-500">
#                           📚 {JSON.parse(msg.sources).length} sources cited
#                         </p>
#                       </div>
#                     )}
#                   </div>
#                 </div>
#               ))}
#               {loading && (
#                 <div className="flex justify-start">
#                   <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-3 shadow-sm">
#                     <Loader2 className="animate-spin text-blue-600" size={20} />
#                   </div>
#                 </div>
#               )}
#               <div ref={messagesEndRef} />
#             </div>

#             {/* Input */}
#             <div className="border-t border-gray-200 bg-white p-4">
#               <div className="max-w-4xl mx-auto">
#                 <div className="flex gap-3">
#                   <input
#                     type="text"
#                     value={input}
#                     onChange={(e) => setInput(e.target.value)}
#                     onKeyPress={handleKeyPress}
#                     placeholder="Ask anything..."
#                     disabled={loading}
#                     className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
#                   />
#                   <button
#                     onClick={sendMessage}
#                     disabled={!input.trim() || loading}
#                     className="px-5 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition flex items-center gap-2"
#                   >
#                     <Send size={18} />
#                   </button>
#                 </div>
#               </div>
#             </div>
#           </>
#         ) : (
#           <div className="flex-1 flex items-center justify-center">
#             <div className="text-center">
#               <h2 className="text-2xl font-semibold text-gray-800 mb-2">
#                 Welcome to Your AI Assistant
#               </h2>
#               <p className="text-gray-600 mb-6">
#                 Create a new conversation to get started
#               </p>
#               <button
#                 onClick={createNewConversation}
#                 className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition flex items-center gap-2 mx-auto"
#               >
#                 <Plus size={18} />
#                 Start New Chat
#               </button>
#             </div>
#           </div>
#         )}
#       </div>
#     </div>
#   );
# }