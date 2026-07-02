import React, { useState, useEffect, useRef } from 'react';
import {
  MessageSquare, FolderOpen, BarChart3, Share2,
  Trash2, Send, Mic, Volume2, Plus, LogOut, FileText,
  FolderPlus, Link2, Eye, Search, BookOpen, Video,
  ChevronRight, Grid, Film, User, Edit3, Save, X
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || `http://${window.location.hostname}:8000`;

function FolderDocumentPicker({ folders, allDocuments, browseFolderId, setBrowseFolderId, selectedDocId, setSelectedDocId, getFileIcon }) {
  if (browseFolderId === 'root') {
    const rootDocs = allDocuments.filter(d => !d.folder_id);
    return (
      <div>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Choose a folder or pick a root file</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(130px,1fr))', gap: '10px', marginBottom: '16px' }}>
          {folders.map(f => {
            const count = allDocuments.filter(d => d.folder_id === f.id).length;
            return (
              <div key={f.id}
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '14px 10px', cursor: 'pointer', textAlign: 'center' }}
                onClick={() => setBrowseFolderId(f.id)}>
                <div style={{ fontSize: '26px', marginBottom: '6px' }}>📁</div>
                <div style={{ fontSize: '12px', color: '#e5e7eb' }}>{f.name}</div>
                <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '2px' }}>{count} file{count === 1 ? '' : 's'}</div>
              </div>
            );
          })}
        </div>
        {rootDocs.length > 0 && (
          <>
            <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '1px' }}>Root Files</div>
            <select className="control-select" style={{ width: '100%', maxWidth: 'none' }}
              value={selectedDocId} onChange={e => setSelectedDocId(e.target.value)}>
              <option value="">Select a document...</option>
              {rootDocs.map(d => <option key={d.id} value={d.id}>{getFileIcon(d.file_type)} {d.filename}</option>)}
            </select>
          </>
        )}
      </div>
    );
  }

  const folder = folders.find(f => f.id === browseFolderId);
  const docsInFolder = allDocuments.filter(d => d.folder_id === browseFolderId);
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <button className="btn-secondary" onClick={() => { setBrowseFolderId('root'); setSelectedDocId(''); }}>← Back</button>
        <span style={{ color: '#00e5ff', fontSize: '13px' }}>📁 {folder?.name}</span>
      </div>
      {docsInFolder.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>No files in this folder.</div>
      ) : (
        <select className="control-select" style={{ width: '100%', maxWidth: 'none' }}
          value={selectedDocId} onChange={e => setSelectedDocId(e.target.value)}>
          <option value="">Select a document...</option>
          {docsInFolder.map(d => <option key={d.id} value={d.id}>{getFileIcon(d.file_type)} {d.filename}</option>)}
        </select>
      )}
    </div>
  );
}

function KnowledgeGraphSVG({ graphData }) {
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef(null);

  if (!graphData || !graphData.nodes?.length) return null;

  const width = 1600, height = 900, padding = 110;
  const xs = graphData.nodes.map(n => n.x);
  const ys = graphData.nodes.map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = (maxX - minX) || 1;
  const spanY = (maxY - minY) || 1;
  const scaleX = x => padding + ((x - minX) / spanX) * (width - 2 * padding);
  const scaleY = y => padding + ((y - minY) / spanY) * (height - 2 * padding);

  const placed = graphData.nodes.map(n => ({ ...n, px: scaleX(n.x), py: scaleY(n.y) }));
  const minDist = 110; // bigger nodes need more breathing room
  for (let pass = 0; pass < 6; pass++) {
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        const a = placed[i], b = placed[j];
        const dx = b.px - a.px, dy = b.py - a.py;
        const dist = Math.hypot(dx, dy) || 0.01;
        if (dist < minDist) {
          const push = (minDist - dist) / 2;
          const ux = dx / dist, uy = dy / dist;
          a.px -= ux * push; a.py -= uy * push;
          b.px += ux * push; b.py += uy * push;
        }
      }
    }
  }
  const nodeById = Object.fromEntries(placed.map(n => [n.id, n]));

  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoom(z => Math.min(3, Math.max(0.4, z + delta)));
  };

  const handleMouseDown = (e) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
  };
  const handleMouseMove = (e) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
  };
  const handleMouseUp = () => { dragRef.current = null; };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      {/* Hint banner — tells the user edges are clickable, since there's no other cue */}
      <div style={{
        position: 'absolute', top: 10, left: 10, zIndex: 5,
        background: 'rgba(11,18,32,0.85)', border: '1px solid rgba(0,240,255,0.25)',
        borderRadius: '8px', padding: '6px 12px', fontSize: '12px', color: '#9ca3af',
        pointerEvents: 'none'
      }}>
        💡 Click any connecting line to see the relationship · Scroll to zoom · Drag to pan
      </div>

      {/* Zoom controls */}
      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 5, display: 'flex', gap: '6px' }}>
        <button onClick={() => setZoom(z => Math.min(3, z + 0.2))} className="btn-secondary" style={{ padding: '4px 10px' }}>+</button>
        <button onClick={() => setZoom(z => Math.max(0.4, z - 0.2))} className="btn-secondary" style={{ padding: '4px 10px' }}>−</button>
        <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="btn-secondary" style={{ padding: '4px 10px' }}>Reset</button>
      </div>

      <svg
        width="100%" height="100%" viewBox={`0 0 ${width} ${height}`}
        style={{ background: '#040711', cursor: dragRef.current ? 'grabbing' : 'grab' }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="7" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill="rgba(148,163,184,0.65)" />
          </marker>
        </defs>

        <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`} transform-origin="center">
          {graphData.edges.map((edge, idx) => {
            const s = nodeById[edge.source], t = nodeById[edge.target];
            if (!s || !t) return null;
            const isSelected = selectedEdge === idx;
            const midX = (s.px + t.px) / 2;
            const midY = (s.py + t.py) / 2;
            const labelText = edge.relationship || 'related to';
            const labelWidth = Math.max(60, labelText.length * 7.5);
            return (
              <g key={idx}>
                <line x1={s.px} y1={s.py} x2={t.px} y2={t.py}
                  stroke={isSelected ? '#00f0ff' : 'rgba(148,163,184,0.4)'}
                  strokeWidth={isSelected ? 3.5 : 1.8}
                  markerEnd="url(#arrowhead)"
                  onClick={() => setSelectedEdge(isSelected ? null : idx)}
                  style={{ cursor: 'pointer' }}
                />
                {/* Invisible wider hit-area so thin lines are easy to click */}
                <line x1={s.px} y1={s.py} x2={t.px} y2={t.py}
                  stroke="transparent" strokeWidth={16}
                  onClick={() => setSelectedEdge(isSelected ? null : idx)}
                  style={{ cursor: 'pointer' }}
                />
                {isSelected && (
                  <g transform={`translate(${midX},${midY})`}>
                    <rect x={-labelWidth / 2} y={-26} width={labelWidth} height={26}
                      rx={13} fill="#0b1220" stroke="#00f0ff" strokeWidth="1.5" />
                    <text x={0} y={-8} fill="#00f0ff" fontSize="13" fontWeight="700" textAnchor="middle">
                      {labelText}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {placed.map((node, idx) => (
            <g key={idx} transform={`translate(${node.px},${node.py})`} className="graph-node">
              <circle r={node.size * 1.6} fill={node.color} stroke="#0b1220" strokeWidth="3" opacity="0.94" />
              <text className="node-label" y={node.size * 1.6 + 20} fontSize="15" fontWeight="600">
                {node.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(localStorage.getItem('docu_logged_in') === 'true');
  const [userId, setUserId] = useState(localStorage.getItem('docu_user_id') ? parseInt(localStorage.getItem('docu_user_id')) : null);
  const [username, setUsername] = useState(localStorage.getItem('docu_username') || '');
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');
  const [regUser, setRegUser] = useState('');
  const [regPass, setRegPass] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [authError, setAuthError] = useState('');

  const [activeTab, setActiveTab] = useState('chat');
  const [folders, setFolders] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [activeFolderId, setActiveFolderId] = useState(null);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showYoutubeInput, setShowYoutubeInput] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [youtubeName, setYoutubeName] = useState('');

  const [chatSessions, setChatSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentSessionTitle, setCurrentSessionTitle] = useState('New Chat');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [searchMode, setSearchMode] = useState('semantic');
  const [talkTarget, setTalkTarget] = useState('all');
  const [enableVoiceOutput, setEnableVoiceOutput] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [secondaryQuery, setSecondaryQuery] = useState('');
  const [secondaryResults, setSecondaryResults] = useState([]);
  const [secondaryModeResults, setSecondaryModeResults] = useState({});
  const [secondaryLoading, setSecondaryLoading] = useState(false);
  const [showSecondaryBar, setShowSecondaryBar] = useState(false);
  const [editingChatId, setEditingChatId] = useState(null);
  const [editingChatTitle, setEditingChatTitle] = useState('');

  const [uploadLoading, setUploadLoading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [returnToTab, setReturnToTab] = useState('chat');

  // Summaries tab
  const [summaryDocId, setSummaryDocId] = useState('');
  const [summaryData, setSummaryData] = useState(null);
  const [summaryTab, setSummaryTab] = useState('short');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [transcriptText, setTranscriptText] = useState('');
  const [hindiSummaries, setHindiSummaries] = useState({});   // { short: '...', detailed: '...', pointers: '...' }
  const [translateLoading, setTranslateLoading] = useState(false);
  const [showHindi, setShowHindi] = useState(false);

  const [analyticsData, setAnalyticsData] = useState({ total_documents: 0, total_folders: 0, total_queries: 0, most_asked_queries: [] });
  const [toastMsg, setToastMsg] = useState('');
  const [toastType, setToastType] = useState('error'); // 'error' | 'success'
  const [graphDocId, setGraphDocId] = useState('');
  const [graphLoading, setGraphLoading] = useState(false);
  const [allDocuments, setAllDocuments] = useState([]);
  const [summaryBrowseFolderId, setSummaryBrowseFolderId] = useState('root');
  const [graphBrowseFolderId, setGraphBrowseFolderId] = useState('root');
  const [accountData, setAccountData] = useState(null);
  const [accountUsername, setAccountUsername] = useState(username);
  const [accountEmail, setAccountEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [accountStatus, setAccountStatus] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const messagesEndRef = useRef(null);

  const getHeaders = () => ({ 'Content-Type': 'application/json', 'X-User-Id': userId ? String(userId) : '' });

  const showToast = (msg, type = 'error') => {
    setToastMsg(msg); setToastType(type);
    setTimeout(() => setToastMsg(''), 4000);
  };

  useEffect(() => {
    if (isLoggedIn && userId) { loadFolders(); loadDocuments(); loadChatSessions(); loadAnalytics(); loadAccountInfo(); loadAllDocuments(); }
  }, [isLoggedIn, userId]);

  useEffect(() => {
    if (activeTab === 'graph') setSidebarCollapsed(true);
  }, [activeTab]);

  useEffect(() => { if (currentSessionId) loadChatMessages(currentSessionId); }, [currentSessionId]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);
  useEffect(() => { if (isLoggedIn && userId) loadDocuments(); }, [activeFolderId]);

  const handleLogin = async (e) => {
    e.preventDefault(); setAuthError('');
    try {
      const r = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: loginUser, password: loginPass }) });
      const data = await r.json();
      if (r.ok) {
        localStorage.setItem('docu_logged_in', 'true');
        localStorage.setItem('docu_user_id', String(data.user_id));
        localStorage.setItem('docu_username', data.username);
        setIsLoggedIn(true); setUserId(data.user_id); setUsername(data.username);
      } else { setAuthError(data.detail || 'Login failed.'); }
    } catch { setAuthError('Cannot connect to backend server.'); }
  };

  const handleRegister = async (e) => {
    e.preventDefault(); setAuthError('');
    try {
      const r = await fetch(`${API_BASE}/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: regUser, password: regPass, email: regEmail }) });
      const data = await r.json();
      if (r.ok) { setIsRegisterMode(false); setLoginUser(regUser); alert('Registration successful! Please log in.'); }
      else { setAuthError(data.detail || 'Registration failed.'); }
    } catch { setAuthError('Cannot connect to backend server.'); }
  };

  const handleLogout = () => {
    localStorage.clear(); setIsLoggedIn(false); setUserId(null); setUsername('');
    setChatMessages([]); setChatSessions([]); setCurrentSessionId(null);
  };

  const loadAccountInfo = async () => {
    try {
      const r = await fetch(`${API_BASE}/auth/me`, { headers: getHeaders() });
      if (r.ok) {
        const data = await r.json();
        setAccountData(data);
        setAccountUsername(data.username || '');
        setAccountEmail(data.email || '');
      }
    } catch { }
  };

  const handleAccountUpdate = async (e) => {
    e.preventDefault();
    setAccountStatus('');
    try {
      const body = {
        username: accountUsername,
        email: accountEmail,
        current_password: currentPassword || null,
        new_password: newPassword || null,
      };
      const r = await fetch(`${API_BASE}/auth/me`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(body) });
      const data = await r.json();
      if (r.ok) {
        setAccountData(data);
        setUsername(data.username);
        localStorage.setItem('docu_username', data.username);
        setCurrentPassword('');
        setNewPassword('');
        setAccountStatus('Account updated.');
      } else {
        setAccountStatus(data.detail || 'Could not update account.');
      }
    } catch {
      setAccountStatus('Could not reach the server.');
    }
  };

  const loadFolders = async () => {
    try { const r = await fetch(`${API_BASE}/folders/list`, { headers: getHeaders() }); if (r.ok) setFolders(await r.json()); else showToast('Could not load folders.'); } catch { showToast('Server unreachable — could not load folders.'); }
  };

  const handleCreateFolder = async (e) => {
    e.preventDefault(); if (!newFolderName.trim()) return;
    try {
      const r = await fetch(`${API_BASE}/folders/create`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ name: newFolderName, parent_id: null }) });
      if (r.ok) { setNewFolderName(''); setShowCreateFolder(false); loadFolders(); }
    } catch { }
  };

  const handleDeleteFolder = async (folderId) => {
    if (!window.confirm("Delete this folder and all its files?")) return;
    try {
      const r = await fetch(`${API_BASE}/folders/${folderId}`, { method: 'DELETE', headers: getHeaders() });
      if (r.ok) { if (activeFolderId === folderId) setActiveFolderId(null); loadFolders(); loadDocuments(); }
    } catch { }
  };

  const loadDocuments = async () => {
    try {
      const url = activeFolderId ? `${API_BASE}/documents/list?folder_id=${activeFolderId}` : `${API_BASE}/documents/list`;
      const r = await fetch(url, { headers: getHeaders() });
      if (r.ok) setDocuments(await r.json());
    } catch { }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    setUploadLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    if (activeFolderId) formData.append('folder_id', String(activeFolderId));
    try {
      const r = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', headers: { 'X-User-Id': String(userId) }, body: formData });
      if (r.ok) { loadDocuments(); loadAnalytics(); showToast('File uploaded & indexed!', 'success'); }
      else { const d = await r.json(); showToast(d.detail || 'Upload failed.'); }
    } catch { showToast('Server unreachable — upload failed.'); }
    setUploadLoading(false); setShowAddMenu(false);
  };

  const handleYoutubeIngest = async (e) => {
    e.preventDefault(); if (!youtubeUrl.trim()) return;
    setUploadLoading(true);
    try {
      const r = await fetch(`${API_BASE}/documents/upload_url`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ url: youtubeUrl, folder_id: activeFolderId, display_name: youtubeName.trim() || null }) });
      if (r.ok) { setYoutubeUrl(''); setYoutubeName(''); setShowYoutubeInput(false); loadDocuments(); loadAllDocuments(); loadAnalytics(); showToast('YouTube transcript indexed!', 'success'); }
      else { const d = await r.json(); showToast(d.detail || "Could not load YouTube transcript."); }
    } catch { showToast('Server unreachable — YouTube ingest failed.'); }
    setUploadLoading(false);
  };

  const handleDeleteDocument = async (docId) => {
    if (!window.confirm("Delete this document?")) return;
    try {
      const r = await fetch(`${API_BASE}/documents/${docId}`, { method: 'DELETE', headers: getHeaders() });
      if (r.ok) { loadDocuments(); loadAnalytics(); }
    } catch { }
  };

  const loadChatSessions = async () => {
    try {
      const r = await fetch(`${API_BASE}/chat/sessions`, { headers: getHeaders() });
      if (r.ok) {
        const data = await r.json(); setChatSessions(data);
        if (data.length > 0 && !currentSessionId) { setCurrentSessionId(data[0].id); setCurrentSessionTitle(data[0].title); }
      }
    } catch { }
  };

  const handleCreateChatSession = async () => {
    try {
      const r = await fetch(`${API_BASE}/chat/sessions`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ title: 'New Chat' }) });
      if (r.ok) {
        const data = await r.json();
        setCurrentSessionId(data.session_id); setCurrentSessionTitle(data.title);
        setChatMessages([]); loadChatSessions(); setActiveTab('chat');
      }
    } catch { }
  };

  const handleRenameChatSession = async (sessionId, event) => {
    event?.stopPropagation();
    const title = editingChatTitle.trim();
    if (!title) return;
    try {
      const r = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
        method: 'PUT', headers: getHeaders(), body: JSON.stringify({ title })
      });
      const data = await r.json();
      if (r.ok) {
        setChatSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: data.title } : s));
        if (currentSessionId === sessionId) setCurrentSessionTitle(data.title);
        setEditingChatId(null);
        setEditingChatTitle('');
        loadChatSessions();
      } else {
        alert(data.detail || 'Could not rename this chat.');
      }
    } catch {
      alert('Could not reach the server to rename this chat.');
    }
  };

  const handleDeleteChatSession = async (sessionId) => {
    if (!window.confirm('Delete this chat?')) return;
    try {
      const r = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, { method: 'DELETE', headers: getHeaders() });
      if (r.ok) {
        const remaining = chatSessions.filter(s => s.id !== sessionId);
        setChatSessions(remaining);
        if (currentSessionId === sessionId) {
          setCurrentSessionId(remaining[0]?.id || null);
          setCurrentSessionTitle(remaining[0]?.title || 'New Chat');
          setChatMessages([]);
        }
      }
    } catch { }
  };

  const loadChatMessages = async (sessId) => {
    try { const r = await fetch(`${API_BASE}/chat/sessions/${sessId}/messages`, { headers: getHeaders() }); if (r.ok) setChatMessages(await r.json()); } catch { }
  };

  const handleSendQuery = async (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    let sessId = currentSessionId;
    if (!sessId) {
      const r = await fetch(`${API_BASE}/chat/sessions`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ title: chatInput.substring(0, 40) }) });
      const newSess = await r.json();
      sessId = newSess.session_id;
      setCurrentSessionId(sessId);
      setCurrentSessionTitle(newSess.title);
      loadChatSessions();
    }

    const tempUserMsg = { role: 'user', content: chatInput };
    setChatMessages(prev => [...prev, tempUserMsg]);
    const promptToSend = chatInput;
    setChatInput(''); setChatLoading(true);

    try {
      const r = await fetch(`${API_BASE}/chat/${sessId}/query`, {
        method: 'POST', headers: getHeaders(),
        body: JSON.stringify({ message: promptToSend, search_mode: searchMode, talk_target: talkTarget })
      });
      if (r.ok) {
        const data = await r.json();
        setChatMessages(prev => [...prev, { role: 'assistant', content: data.response, citations: data.citations || [] }]);
        const nextTitle = data.session_title;
        if (nextTitle && nextTitle !== 'New Chat') {
          setCurrentSessionTitle(nextTitle);
          setChatSessions(prev => prev.map(s => s.id === sessId ? { ...s, title: nextTitle } : s));
        }
        loadChatSessions();
        if (enableVoiceOutput && 'speechSynthesis' in window) {
          const synth = window.speechSynthesis; synth.cancel();
          const utter = new SpeechSynthesisUtterance(data.response);
          utter.lang = 'en-US'; synth.speak(utter);
        }
        loadAnalytics();
      }
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Connection error — could not reach the server.' }]);
      showToast('Connection error. Is the backend running?');
    }
    setChatLoading(false);
  };

  const [secondaryError, setSecondaryError] = useState('');

  const handleSecondarySearch = async (e) => {
    e.preventDefault();
    const trimmed = secondaryQuery.trim();
    setSecondaryError('');
    setSecondaryModeResults({});
    if (trimmed.length < 3) {
      setSecondaryError('Type at least a few characters to search.');
      setSecondaryResults([]);
      return;
    }
    setSecondaryLoading(true); setSecondaryResults([]);
    try {
      const r = await fetch(`${API_BASE}/search/preview`, {
        method: 'POST', headers: getHeaders(),
        body: JSON.stringify({ query: trimmed, search_mode: searchMode, talk_target: talkTarget })
      });
      const data = r.ok ? await r.json() : { results: [] };
      setSecondaryResults(data.results || []);
      if ((data.results || []).length === 0) setSecondaryError(`No ${searchMode} matches found in the selected scope.`);
    } catch {
      setSecondaryError('Could not reach the server.');
    }
    setSecondaryLoading(false);
  };

  const loadSummaries = async () => {
    if (!summaryDocId) return;
    setSummaryLoading(true); setSummaryData(null); setTranscriptText('');
    setHindiSummaries({}); setShowHindi(false);
    try {
      const r = await fetch(`${API_BASE}/documents/${summaryDocId}/summaries`, { headers: getHeaders() });
      if (r.ok) setSummaryData(await r.json());
    } catch { }
    setSummaryLoading(false);
  };

  const translateSummary = async () => {
    if (!summaryData) return;
    // If already translated for all tabs, just toggle display
    if (hindiSummaries.short && hindiSummaries.detailed && hindiSummaries.pointers) {
      setShowHindi(h => !h);
      return;
    }
    setTranslateLoading(true);
    try {
      const types = ['short', 'detailed', 'pointers'];
      const texts = {
        short: summaryData.summary_short || '',
        detailed: summaryData.summary_detailed || '',
        pointers: summaryData.summary_pointers || '',
      };
      const results = {};
      for (const t of types) {
        if (!texts[t]) { results[t] = ''; continue; }
        const r = await fetch(`${API_BASE}/translate/hindi`, {
          method: 'POST', headers: getHeaders(),
          body: JSON.stringify({ text: texts[t], summary_type: t }),
        });
        if (r.ok) { const d = await r.json(); results[t] = d.translated || ''; }
        else results[t] = 'Translation failed.';
      }
      setHindiSummaries(results);
      setShowHindi(true);
    } catch { showToast('Translation failed — check server connection.'); }
    setTranslateLoading(false);
  };

  const loadAnalytics = async () => {
    try { const r = await fetch(`${API_BASE}/analytics/summary`, { headers: getHeaders() }); if (r.ok) setAnalyticsData(await r.json()); } catch { }
  };

  const loadAllDocuments = async () => {
    try {
      const r = await fetch(`${API_BASE}/documents/list`, { headers: getHeaders() });
      if (r.ok) setAllDocuments(await r.json());
    } catch { }
  };

  const [graphData, setGraphData] = useState(null);
  const [graphStats, setGraphStats] = useState(null);

  const loadGraphData = async (forceRefresh = false) => {
    if (!graphDocId) return;
    setGraphLoading(true); setGraphData(null); setGraphStats(null);
    try {
      const r = await fetch(`${API_BASE}/documents/${graphDocId}/graph`, { headers: getHeaders() });
      if (r.ok) {
        const data = await r.json();
        setGraphData(data.graph_data);
        setGraphStats(data.graph_data?.stats || null);
      }
    } catch { }
    setGraphLoading(false);
  };

  const getDocById = (docId) => documents.find(d => String(d.id) === String(docId));
  const getDocByFilename = (filename) => documents.find(d => d.filename === filename || d.file_path === filename);

  const getYoutubeEmbedUrl = (url = '') => {
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/);
    return match ? `https://www.youtube.com/embed/${match[1]}` : url;
  };

  const openDocument = (docOrId, pageNumber = 1) => {
    const doc = typeof docOrId === 'object' ? docOrId : getDocById(docOrId);
    if (!doc) return;
    setReturnToTab(prevReturnToTab => (selectedDoc ? prevReturnToTab : activeTab));
    setSelectedDoc(doc);
    setSelectedPage(pageNumber || 1);
    setActiveTab('explorer');
  };

  const closeDocumentViewer = () => {
    setSelectedDoc(null);
    setActiveTab(returnToTab);
  };

  const getDocumentViewSrc = (doc, pageNumber = selectedPage) => {
    if (!doc) return '';
    if (doc.file_type === 'youtube') return getYoutubeEmbedUrl(doc.file_path || doc.filename);
    const base = `${API_BASE}/documents/${doc.id}/view?user_id=${userId}`;
    if (doc.file_type === 'pdf') return `${base}#page=${pageNumber || 1}`;
    return base;
  };

  const handleCitationClick = (e) => {
    const target = e.target.closest?.('.citation-badge');
    if (!target) return;
    const docId = target.dataset.docId;
    const filename = target.dataset.filename;
    const page = parseInt(target.dataset.page || '1', 10);
    const doc = docId ? getDocById(docId) : getDocByFilename(filename);
    if (doc) openDocument(doc, page);
  };

  const toggleSpeechRecognition = () => {
    if (!window.isSecureContext) {
      alert("Voice input needs a secure browser context. Use http://localhost:5173 or HTTPS, then allow microphone permission.");
      return;
    }
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) { alert("Voice input is not supported in this browser. Try Chrome or Edge."); return; }
    if (isListening) { window.recognitionInstance?.stop(); setIsListening(false); return; }
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRec();
    rec.continuous = false; rec.interimResults = false; rec.lang = 'en-US';
    rec.onstart = () => setIsListening(true);
    rec.onresult = (event) => setChatInput(prev => prev + ' ' + event.results[0][0].transcript);
    rec.onerror = (event) => {
      setIsListening(false);
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        alert("Microphone permission is blocked. Click the lock/tune icon in the browser address bar, allow Microphone for this site, then refresh.");
      } else if (event.error === 'no-speech') {
        alert("I did not hear speech. Try again and speak after the listening indicator appears.");
      } else {
        alert(`Voice input failed: ${event.error || 'unknown error'}`);
      }
    };
    rec.onend = () => setIsListening(false);
    window.recognitionInstance = rec; rec.start();
  };

  const renderMessageContent = (content) => {
    // Convert markdown tables to HTML tables
    const lines = content.split('\n');
    let html = '';
    let inTable = false;
    let tableHtml = '';
    let tableRowCount = 0;  // track rows within the current table, not global line index

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.trim().startsWith('|')) {
        if (!inTable) { inTable = true; tableHtml = '<table style="border-collapse:collapse;width:100%;margin:12px 0;font-size:13px">'; tableRowCount = 0; }
        const isSeparator = line.replace(/\|/g, '').trim().replace(/[-:\s]/g, '') === '';
        if (!isSeparator) {
          // First non-separator row in this table is always the header
          const isHeader = tableRowCount === 0;
          const tag = isHeader ? 'th' : 'td';
          const cells = line.split('|').filter((_, idx) => idx > 0 && idx < line.split('|').length - 1);
          tableHtml += '<tr>' + cells.map(c => `<${tag} style="border:1px solid rgba(255,255,255,0.15);padding:8px 14px;text-align:left;background:${isHeader ? 'rgba(0,229,255,0.08)' : 'transparent'}">${c.trim()}</${tag}>`).join('') + '</tr>';
          tableRowCount++;
        }
      } else {
        if (inTable) { html += tableHtml + '</table>'; inTable = false; tableHtml = ''; tableRowCount = 0; }
        html += line
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          .replace(/\[([^,\]]+),\s*Page\s*(\d+)\]/g, (match, filename, page) => {
            const doc = getDocByFilename(filename.trim());
            const docAttr = doc ? ` data-doc-id="${doc.id}"` : '';
            return `<span class="citation-badge"${docAttr} data-filename="${filename.trim()}" data-page="${page}">${filename.trim()}, Page ${page}</span>`;
          })
          + '<br/>';
      }
    }
    if (inTable) html += tableHtml + '</table>';
    return html;
  };

  const getFileIcon = (fileType) => {
    const icons = { pdf: '📄', docx: '📝', doc: '📝', pptx: '📊', ppt: '📊', txt: '📃', mp4: '🎬', youtube: '▶️' };
    return icons[fileType?.toLowerCase()] || '📁';
  };

  const getCategoryColor = (cat) => {
    const colors = { Research: '#3b82f6', Finance: '#10b981', Legal: '#ef4444', Education: '#f59e0b', Technology: '#8b5cf6' };
    return colors[cat] || '#6b7280';
  };

  if (!isLoggedIn) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-title">🧠 DocuIntellect</div>
          <div className="auth-subtitle">AI-Powered Document Intelligence Hub</div>
          {authError && <div style={{ color: '#ef4444', fontSize: '13px', marginBottom: '15px' }}>{authError}</div>}
          {!isRegisterMode ? (
            <form onSubmit={handleLogin}>
              <div className="auth-form-group"><label className="auth-label">Username</label><input type="text" className="auth-input" value={loginUser} onChange={e => setLoginUser(e.target.value)} placeholder="Enter username" required /></div>
              <div className="auth-form-group"><label className="auth-label">Password</label><input type="password" className="auth-input" value={loginPass} onChange={e => setLoginPass(e.target.value)} placeholder="Enter password" required /></div>
              <button type="submit" className="auth-btn">Sign In</button>
              <div className="auth-toggle-link" onClick={() => setIsRegisterMode(true)}>Need an account? Register</div>
            </form>
          ) : (
            <form onSubmit={handleRegister}>
              <div className="auth-form-group"><label className="auth-label">Username</label><input type="text" className="auth-input" value={regUser} onChange={e => setRegUser(e.target.value)} placeholder="Create username" required /></div>
              <div className="auth-form-group"><label className="auth-label">Email (Optional)</label><input type="email" className="auth-input" value={regEmail} onChange={e => setRegEmail(e.target.value)} placeholder="Enter email" /></div>
              <div className="auth-form-group"><label className="auth-label">Password</label><input type="password" className="auth-input" value={regPass} onChange={e => setRegPass(e.target.value)} placeholder="Create password" required /></div>
              <button type="submit" className="auth-btn">Create Account</button>
              <div className="auth-toggle-link" onClick={() => setIsRegisterMode(false)}>Already have an account? Sign In</div>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      <button
        className="sidebar-toggle-btn"
        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        title={sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
      >
        <ChevronRight size={16} style={{ transform: sidebarCollapsed ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform 0.2s' }} />
      </button>
      {/* Sidebar */}
      <div className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <button type="button" className="sidebar-profile profile-button" onClick={() => setActiveTab('account')} title="Account">
            <div className="profile-avatar">{username.substring(0, 2).toUpperCase()}</div>
            <div className="profile-name">{username}</div>
          </button>
          <button className="logout-icon-btn" onClick={handleLogout}><LogOut size={16} /></button>
        </div>

        <div className="sidebar-nav">
          {[
            { id: 'chat', icon: <MessageSquare size={16} />, label: 'RAG Agent Chat' },
            { id: 'explorer', icon: <FolderOpen size={16} />, label: 'Document Vault' },
            { id: 'summaries', icon: <BookOpen size={16} />, label: 'Summaries' },
            { id: 'analytics', icon: <BarChart3 size={16} />, label: 'Analytics' },
            { id: 'graph', icon: <Share2 size={16} />, label: 'Knowledge Graph' },
          ].map(tab => (
            <div key={tab.id} className={`nav-item ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>
              {tab.icon}<span>{tab.label}</span>
            </div>
          ))}
        </div>

        <div className="sidebar-section">
          <div>
            <div className="sidebar-section-title">
              <span>Folders</span>
              <FolderPlus size={12} style={{ cursor: 'pointer' }} onClick={() => setShowCreateFolder(!showCreateFolder)} />
            </div>
            {showCreateFolder && (
              <form onSubmit={handleCreateFolder} style={{ marginBottom: '10px' }}>
                <input type="text" className="auth-input" style={{ padding: '6px 10px', fontSize: '12px' }} placeholder="Folder name..." value={newFolderName} onChange={e => setNewFolderName(e.target.value)} autoFocus />
              </form>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <div className={`folder-item ${activeFolderId === null ? 'active' : ''}`} onClick={() => { setActiveFolderId(null); setActiveTab('explorer'); }}>
                <span>Root Directory</span>
              </div>
              {folders.map(f => (
                <div key={f.id} className={`folder-item ${activeFolderId === f.id ? 'active' : ''}`} onClick={() => { setActiveFolderId(f.id); setActiveTab('explorer'); }}>
                  <span>📁 {f.name}</span>
                  <div className="folder-actions" onClick={e => e.stopPropagation()}>
                    <Trash2 size={12} style={{ color: '#ef4444', cursor: 'pointer' }} onClick={() => handleDeleteFolder(f.id)} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginTop: '20px' }}>
            <div className="sidebar-section-title"><span>Chat History</span></div>
            <button className="new-chat-btn" onClick={handleCreateChatSession}><Plus size={12} /> New Conversation</button>
            <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
              {chatSessions.map(s => (
                <div key={s.id} className={`history-item ${currentSessionId === s.id && activeTab === 'chat' ? 'active' : ''}`}
                  onClick={() => { if (editingChatId !== s.id) { setCurrentSessionId(s.id); setCurrentSessionTitle(s.title); setActiveTab('chat'); } }}>
                  {editingChatId === s.id ? (
                    <div className="history-edit-row" onClick={e => e.stopPropagation()}>
                      <input className="history-edit-input" value={editingChatTitle} onChange={e => setEditingChatTitle(e.target.value)} autoFocus
                        onKeyDown={e => { if (e.key === 'Enter') handleRenameChatSession(s.id, e); if (e.key === 'Escape') setEditingChatId(null); }} />
                      <button type="button" className="history-icon-btn" onClick={(e) => handleRenameChatSession(s.id, e)}><Save size={12} /></button>
                      <button type="button" className="history-icon-btn" onClick={(e) => { e.stopPropagation(); setEditingChatId(null); }}><X size={12} /></button>
                    </div>
                  ) : (
                    <span className="history-display-row">
                      <span className="history-title"> {s.title || 'New Chat'}</span>
                      <span className="history-actions" onClick={e => e.stopPropagation()}>
                        <button type="button" className="history-icon-btn" onClick={(e) => { e.stopPropagation(); setEditingChatId(s.id); setEditingChatTitle(s.title || ''); }}><Edit3 size={12} /></button>
                        <button type="button" className="history-icon-btn danger" onClick={(e) => { e.stopPropagation(); handleDeleteChatSession(s.id); }}><Trash2 size={12} /></button>
                      </span>
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="main-content">

        {/* CHAT TAB */}
        {activeTab === 'chat' && (
          <div className="chat-workspace">
            <div className="chat-header">
              <div className="chat-header-title">Chat: {currentSessionTitle}</div>
              <div className="chat-header-controls">
                <select className="control-select" value={talkTarget} onChange={e => setTalkTarget(e.target.value)}>
                  <option value="all">🎯 Entire Database</option>
                  {folders.map(f => <option key={f.id} value={`folder:${f.id}`}>📁 {f.name}</option>)}
                  {documents.map(d => <option key={d.id} value={`file:${d.id}`}>📄 {d.filename.substring(0, 20)}...</option>)}
                </select>

                <div className="toggle-group">
                  <div className={`toggle-option ${searchMode === 'hybrid' ? 'active' : ''}`} onClick={() => setSearchMode('hybrid')}>
                    Hybrid
                  </div>
                  <div className={`toggle-option ${searchMode === 'semantic' ? 'active' : ''}`} onClick={() => setSearchMode('semantic')}>
                    Semantic
                  </div>
                  <div className={`toggle-option ${searchMode === 'keyword' ? 'active' : ''}`} onClick={() => setSearchMode('keyword')}>
                    Keyword
                  </div>
                </div>

                <button className="chat-action-btn" onClick={() => setShowSecondaryBar(!showSecondaryBar)} title="Search documents">
                  <Search size={16} />
                </button>

                <button className="chat-action-btn" style={{ color: enableVoiceOutput ? '#00f0ff' : '#9ca3af' }} onClick={() => setEnableVoiceOutput(!enableVoiceOutput)}>
                  <Volume2 size={16} />
                </button>
              </div>
            </div>

            {/* Secondary retrieval search bar */}
            {showSecondaryBar && (
              <div style={{ padding: '10px 20px', borderBottom: '1px solid rgba(59,130,246,0.1)', background: 'rgba(0,0,0,0.2)' }}>
                <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '6px' }}>Search documents with {searchMode === 'semantic' ? 'semantic meaning' : 'keyword'} matching</div>
                <form onSubmit={handleSecondarySearch} style={{ display: 'flex', gap: '8px' }}>
                  <input type="text" className="chat-text-input" style={{ fontSize: '12px', padding: '6px 12px' }}
                    placeholder={searchMode === 'semantic' ? 'Search by meaning...' : 'Search by exact words...'} value={secondaryQuery} onChange={e => setSecondaryQuery(e.target.value)} />
                  <button type="submit" className="chat-send-btn" disabled={secondaryLoading}>
                    <Search size={13} />
                  </button>
                  <button type="button" className="chat-action-btn" onClick={() => { setShowSecondaryBar(false); setSecondaryResults([]); }}>✕</button>
                </form>
                {secondaryLoading && <div style={{ fontSize: '12px', color: '#00f0ff', marginTop: '6px' }}>Searching...</div>}
                {!secondaryLoading && secondaryError && (
                  <div style={{ fontSize: '12px', color: '#f59e0b', marginTop: '6px' }}>{secondaryError}</div>
                )}
                {secondaryResults.length > 0 && (
                  <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '220px', overflowY: 'auto' }}>
                    {secondaryResults.map((r, i) => (
                      <div key={i} onClick={() => openDocument(r.document_id, r.page_number)}
                        style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '6px', padding: '8px 10px', fontSize: '12px', color: '#9ca3af', cursor: 'pointer' }}>
                        <div style={{ color: '#00f0ff', marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
                          <span>{r.filename} p.{r.page_number} · {r.content_type} · {(r.matched_by || []).filter(Boolean).join(' + ')}</span>
                          {typeof r.score === 'number' && <span style={{ color: '#6b7280' }}>relevance {r.score.toFixed(3)}</span>}
                        </div>
                        <div style={{ lineHeight: 1.4 }}>{(r.text_content || '').slice(0, 260)}{(r.text_content || '').length > 260 ? '...' : ''}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="chat-messages-scroll">
              {chatMessages.length === 0 ? (
                <div style={{ textAlign: 'center', marginTop: '100px', color: '#6b7280' }}>
                  <MessageSquare size={40} style={{ marginBottom: '10px', opacity: 0.3 }} />
                  <h4>Ask anything about your documents</h4>
                  <p style={{ fontSize: '13px', marginTop: '4px' }}>Select scope and search mode above.</p>
                </div>
              ) : (
                chatMessages.map((msg, i) => (
                  <div key={i} className={`msg-row ${msg.role === 'user' ? 'user' : 'assistant'}`}>
                    <div className="msg-bubble">
                      {msg.role === 'assistant'
                        ? <span onClick={handleCitationClick} dangerouslySetInnerHTML={{ __html: renderMessageContent(msg.content) }} />
                        : msg.content}
                      {msg.role === 'assistant' && msg.citations?.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                          {msg.citations.map((c, idx) => (
                            <button key={idx} className="citation-badge" style={{ border: '1px solid rgba(59,130,246,0.25)', cursor: 'pointer' }}
                              onClick={() => openDocument(c.document_id, c.page_number)}>
                              {c.filename}, Page {c.page_number}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              {chatLoading && <div className="msg-row assistant"><div className="msg-bubble" style={{ opacity: 0.5 }}>Thinking...</div></div>}
              <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-area">
              {!window.isSecureContext && (
                <div className="mic-warning">
                  Microphone recording needs a secure origin. Open this app at http://localhost:5173 on this machine, or serve it over HTTPS.
                </div>
              )}
              <form onSubmit={handleSendQuery} className="chat-input-container">
                <button type="button" className="chat-action-btn" style={{ color: isListening ? '#ef4444' : '#9ca3af' }} onClick={toggleSpeechRecognition}>
                  <Mic size={16} />
                </button>
                <input type="text" className="chat-text-input" placeholder={isListening ? "Listening..." : "Ask anything about your documents..."}
                  value={chatInput} onChange={e => setChatInput(e.target.value)} disabled={chatLoading} />
                <button type="submit" className="chat-send-btn" disabled={chatLoading}><Send size={14} /></button>
              </form>
            </div>
          </div>
        )}

        {/* DOCUMENT VAULT - Google Drive Style */}
        {activeTab === 'explorer' && (
          <div className="pane-container" style={{ position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div>
                <h2 className="pane-title">Document Vault</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280' }}>
                  <span style={{ cursor: 'pointer', color: '#9ca3af' }} onClick={() => setActiveFolderId(null)}>Root</span>
                  {activeFolderId && <>
                    <ChevronRight size={12} />
                    <span style={{ color: '#00e5ff' }}>{folders.find(f => f.id === activeFolderId)?.name}</span>
                  </>}
                </div>
              </div>
            </div>

            {/* Folders row */}
            {folders.length > 0 && (
              <div style={{ marginBottom: '24px' }}>
                <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Folders</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(140px,1fr))', gap: '12px' }}>
                  {folders.map(f => (
                    <div key={f.id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '16px 12px', cursor: 'pointer', textAlign: 'center', position: 'relative', transition: 'all 0.2s' }}
                      onClick={() => setActiveFolderId(f.id)}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(59,130,246,0.08)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}>
                      <div style={{ fontSize: '32px', marginBottom: '8px' }}>📁</div>
                      <div style={{ fontSize: '12px', color: '#e5e7eb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
                      <button style={{ position: 'absolute', top: '6px', right: '6px', background: 'none', border: 'none', cursor: 'pointer', opacity: 0.4, color: '#ef4444', padding: '2px' }}
                        onClick={e => { e.stopPropagation(); handleDeleteFolder(f.id); }}>
                        <Trash2 size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Documents grid */}
            <div>
              <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Files</div>
              {documents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280', border: '2px dashed rgba(255,255,255,0.06)', borderRadius: '16px' }}>
                  <FileText size={32} style={{ marginBottom: '12px', opacity: 0.3 }} />
                  <p>No files here. Click the + button to add files.</p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(140px,1fr))', gap: '12px' }}>
                  {documents.map(d => (
                    <div key={d.id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '16px 12px', cursor: 'pointer', textAlign: 'center', position: 'relative', transition: 'all 0.2s' }}
                      onClick={() => openDocument(d, 1)}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.06)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}>
                      <div style={{ fontSize: '32px', marginBottom: '8px' }}>{getFileIcon(d.file_type)}</div>
                      <div style={{ fontSize: '11px', color: '#e5e7eb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: '6px' }} title={d.filename}>{d.filename}</div>
                      <div style={{ display: 'inline-block', fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: getCategoryColor(d.category) + '22', color: getCategoryColor(d.category), border: `1px solid ${getCategoryColor(d.category)}44` }}>
                        {d.category}
                      </div>
                      <div style={{ position: 'absolute', top: '6px', right: '6px', display: 'flex', gap: '4px' }}>
                        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '2px', opacity: 0.5 }}
                          onClick={e => { e.stopPropagation(); handleDeleteDocument(d.id); }}>
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* YouTube input bar */}
            {showYoutubeInput && (
              <div style={{ position: 'fixed', bottom: '90px', right: '30px', background: '#0d1117', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '12px', padding: '16px', width: '320px', zIndex: 1000, boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
                <div style={{ fontSize: '13px', color: '#9ca3af', marginBottom: '10px' }}>▶️ Add YouTube Video</div>
                <form onSubmit={handleYoutubeIngest} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <input
                    type="url" className="auth-input" placeholder="Paste YouTube URL..."
                    value={youtubeUrl} onChange={e => setYoutubeUrl(e.target.value)} disabled={uploadLoading}
                  />
                  <input
                    type="text" className="auth-input" placeholder="Custom name (optional — auto-detected if blank)"
                    value={youtubeName} onChange={e => setYoutubeName(e.target.value)} disabled={uploadLoading}
                  />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button type="submit" className="btn-primary" disabled={uploadLoading} style={{ flex: 1 }}>Ingest</button>
                    <button type="button" className="btn-secondary" onClick={() => { setShowYoutubeInput(false); setYoutubeName(''); }}>Cancel</button>
                  </div>
                </form>
              </div>
            )}

            {/* Floating + button */}
            <div style={{ position: 'fixed', bottom: '30px', right: '30px', zIndex: 999 }}>
              {showAddMenu && (
                <div style={{ position: 'absolute', bottom: '60px', right: '0', background: '#0d1117', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '12px', padding: '8px', minWidth: '160px', boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
                  {[
                    { label: '📄 PDF', accept: '.pdf' },
                    { label: '📝 DOCX', accept: '.docx,.doc' },
                    { label: '📊 PPTX', accept: '.pptx,.ppt' },
                    { label: '📃 TXT', accept: '.txt,.md' },
                    { label: '🎬 MP4', accept: '.mp4' },
                  ].map(opt => (
                    <div key={opt.label} style={{ padding: '8px 12px', cursor: 'pointer', borderRadius: '8px', fontSize: '13px', color: '#e5e7eb', transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(59,130,246,0.15)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      onClick={() => { document.getElementById('vault-upload-input').accept = opt.accept; document.getElementById('vault-upload-input').click(); }}>
                      {opt.label}
                    </div>
                  ))}
                  <div style={{ padding: '8px 12px', cursor: 'pointer', borderRadius: '8px', fontSize: '13px', color: '#e5e7eb', borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: '4px' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(59,130,246,0.15)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    onClick={() => { setShowYoutubeInput(true); setShowAddMenu(false); }}>
                    ▶️ YouTube Link
                  </div>
                  <div style={{ padding: '8px 12px', cursor: 'pointer', borderRadius: '8px', fontSize: '13px', color: '#e5e7eb' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(59,130,246,0.15)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    onClick={() => { setShowCreateFolder(true); setShowAddMenu(false); }}>
                    📁 New Folder
                  </div>
                </div>
              )}
              <button onClick={() => setShowAddMenu(!showAddMenu)}
                style={{ width: '52px', height: '52px', borderRadius: '50%', background: 'linear-gradient(135deg,#2563eb,#00e5ff)', border: 'none', cursor: 'pointer', fontSize: '24px', color: 'white', boxShadow: '0 4px 20px rgba(37,99,235,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'transform 0.2s' }}
                onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.1)'}
                onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}>
                <Plus size={22} />
              </button>
              <input type="file" id="vault-upload-input" style={{ display: 'none' }} onChange={handleFileUpload} disabled={uploadLoading} />
            </div>

            {uploadLoading && (
              <div style={{ position: 'fixed', bottom: '100px', right: '100px', background: 'rgba(0,229,255,0.1)', border: '1px solid rgba(0,229,255,0.3)', borderRadius: '8px', padding: '10px 16px', fontSize: '13px', color: '#00f0ff' }}>
                Uploading & indexing...
              </div>
            )}

            {selectedDoc && (
              <div style={{ position: 'fixed', inset: '24px', zIndex: 1200, background: '#070b13', border: '1px solid rgba(0,229,255,0.25)', borderRadius: '12px', boxShadow: '0 20px 80px rgba(0,0,0,0.65)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ height: '52px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                    <span style={{ fontSize: '20px' }}>{getFileIcon(selectedDoc.file_type)}</span>
                    <div style={{ fontSize: '14px', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedDoc.filename}</div>
                    {selectedDoc.file_type === 'pdf' && <div style={{ fontSize: '12px', color: '#9ca3af' }}>Page {selectedPage}</div>}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    {selectedDoc.file_type === 'pdf' && (
                      <>
                        <button className="btn-secondary" onClick={() => setSelectedPage(p => Math.max(1, p - 1))}>Prev</button>
                        <button className="btn-secondary" onClick={() => setSelectedPage(p => p + 1)}>Next</button>
                      </>
                    )}
                    <a className="btn-secondary" href={getDocumentViewSrc(selectedDoc)} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>Open</a>
                    <button className="btn-secondary" onClick={closeDocumentViewer}>Close</button>
                  </div>
                </div>
                <div style={{ flex: 1, background: '#030712' }}>
                  {selectedDoc.file_type === 'mp4' ? (
                    <video src={getDocumentViewSrc(selectedDoc)} controls style={{ width: '100%', height: '100%', background: '#000' }} />
                  ) : selectedDoc.file_type === 'youtube' ? (
                    <iframe title={selectedDoc.filename} src={getDocumentViewSrc(selectedDoc)} style={{ width: '100%', height: '100%', border: 0 }} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />
                  ) : (
                    <iframe key={`${selectedDoc.id}-${selectedPage}`} title={selectedDoc.filename} src={getDocumentViewSrc(selectedDoc)} style={{ width: '100%', height: '100%', border: 0, background: '#111827' }} />
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* SUMMARIES TAB */}
        {activeTab === 'summaries' && (
          <div className="pane-container">
            <div>
              <h2 className="pane-title">Document Summaries</h2>
              <p className="pane-subtitle">Select a document to generate AI summaries or view video transcripts.</p>
            </div>

            <div className="glass-panel" style={{ marginBottom: '20px' }}>
              <FolderDocumentPicker
                folders={folders}
                allDocuments={allDocuments}
                browseFolderId={summaryBrowseFolderId}
                setBrowseFolderId={setSummaryBrowseFolderId}
                selectedDocId={summaryDocId}
                setSelectedDocId={setSummaryDocId}
                getFileIcon={getFileIcon}
              />
              <button className="btn-primary" style={{ marginTop: '14px' }} onClick={loadSummaries} disabled={!summaryDocId || summaryLoading}>
                {summaryLoading ? 'Loading...' : '✨ Generate'}
              </button>
            </div>

            {summaryData && (
              <div className="glass-panel">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <h3 style={{ color: '#00f0ff' }}>{summaryData.filename}</h3>
                  <button className="btn-secondary" onClick={() => openDocument(summaryDocId, 1)}>Open document</button>
                </div>

                {/* Check if it's a video */}
                {(summaryData.filename?.includes('youtube') || summaryData.filename?.endsWith('.mp4')) && (
                  <div style={{ marginBottom: '20px', padding: '12px', background: 'rgba(239,68,68,0.08)', borderRadius: '8px', border: '1px solid rgba(239,68,68,0.2)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: '#ef4444', fontSize: '13px' }}>
                      <Film size={14} /> Video / YouTube Content
                    </div>
                    <div style={{ fontSize: '12px', color: '#9ca3af' }}>Summaries are generated from the transcript of this video.</div>
                  </div>
                )}

                <div className="summary-tab-headers">
                  {['short', 'detailed', 'pointers'].map(t => (
                    <button key={t} className={`summary-tab-btn ${summaryTab === t ? 'active' : ''}`} onClick={() => setSummaryTab(t)}>
                      {t === 'short' ? 'Short' : t === 'detailed' ? 'Detailed' : 'Key Takeaways'}
                    </button>
                  ))}
                </div>

                <div className="summary-content-box" style={{ whiteSpace: 'pre-line', lineHeight: '1.7' }}>
                  {summaryTab === 'short' && (summaryData.summary_short || 'No summary available.')}
                  {summaryTab === 'detailed' && (summaryData.summary_detailed || 'No summary available.')}
                  {summaryTab === 'pointers' && (summaryData.summary_pointers || 'No key takeaways.')}
                </div>

                {/* Hindi Translation */}
                <div style={{ marginTop: '14px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <button
                    className="btn-secondary"
                    onClick={translateSummary}
                    disabled={translateLoading}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                  >
                    {translateLoading ? '⏳ Translating...' : showHindi ? '🌐 Hide Hindi' : '🇮🇳 Translate to Hindi'}
                  </button>
                  {showHindi && hindiSummaries[summaryTab] && (
                    <span style={{ fontSize: '11px', color: '#6b7280' }}>Hindi translation below</span>
                  )}
                </div>

                {showHindi && hindiSummaries[summaryTab] && (
                  <div className="summary-content-box" style={{ whiteSpace: 'pre-line', lineHeight: '1.9', marginTop: '10px', borderColor: 'rgba(251,191,36,0.2)', background: 'rgba(251,191,36,0.04)', fontFamily: "'Noto Sans Devanagari', sans-serif", fontSize: '14px' }}>
                    <div style={{ fontSize: '11px', color: '#fbbf24', marginBottom: '8px', fontFamily: 'inherit' }}>🇮🇳 हिंदी अनुवाद</div>
                    {hindiSummaries[summaryTab]}
                  </div>
                )}
              </div>
            )}

            {!summaryData && !summaryLoading && (
              <div style={{ textAlign: 'center', padding: '60px', color: '#6b7280', border: '2px dashed rgba(255,255,255,0.06)', borderRadius: '16px' }}>
                <BookOpen size={32} style={{ marginBottom: '12px', opacity: 0.3 }} />
                <p>Select a document above and click Generate to view summaries.</p>
              </div>
            )}
          </div>
        )}

        {/* ACCOUNT TAB */}
        {activeTab === 'account' && (
          <div className="pane-container">
            <div>
              <h2 className="pane-title">Account</h2>
              <p className="pane-subtitle">View your account details and update your username or password.</p>
            </div>
            <div className="glass-panel account-panel">
              <div className="account-summary">
                <div className="profile-avatar large">{username.substring(0, 2).toUpperCase()}</div>
                <div>
                  <h3>{accountData?.username || username}</h3>
                  <p>User ID: {userId}</p>
                  <p>Email: {accountData?.email || 'Not set'}</p>
                </div>
              </div>
              <form onSubmit={handleAccountUpdate} className="account-form">
                <div className="auth-form-group">
                  <label className="auth-label">Username</label>
                  <input className="auth-input" value={accountUsername} onChange={e => setAccountUsername(e.target.value)} required />
                </div>
                <div className="auth-form-group">
                  <label className="auth-label">Email</label>
                  <input className="auth-input" type="email" value={accountEmail} onChange={e => setAccountEmail(e.target.value)} placeholder="Optional email" />
                </div>
                <div className="auth-form-group">
                  <label className="auth-label">Current Password</label>
                  <input className="auth-input" type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Required only when changing password" />
                </div>
                <div className="auth-form-group">
                  <label className="auth-label">New Password</label>
                  <input className="auth-input" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Leave blank to keep current password" />
                </div>
                {accountStatus && <div className="account-status">{accountStatus}</div>}
                <button type="submit" className="btn-primary">Save Changes</button>
              </form>
            </div>
          </div>
        )}

        {/* ANALYTICS TAB */}
        {activeTab === 'analytics' && (
          <div className="pane-container">
            <div><h2 className="pane-title">System Analytics</h2><p className="pane-subtitle">Usage statistics and document insights.</p></div>
            <div className="kpi-row">
              <div className="kpi-card"><div className="kpi-title">Total Folders</div><div className="kpi-value">{analyticsData.total_folders}</div></div>
              <div className="kpi-card"><div className="kpi-title">Ingested Files</div><div className="kpi-value">{analyticsData.total_documents}</div></div>
              <div className="kpi-card"><div className="kpi-title">Queries Answered</div><div className="kpi-value">{analyticsData.total_queries}</div></div>
            </div>
            <div className="chart-row">
              <div className="glass-panel">
                <h3>Document Categories</h3>
                <div style={{ marginTop: '20px' }}>
                  {documents.length === 0 ? <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>No files yet.</div> : (
                    <div className="circle-chart-box">
                      <svg width="150" height="150" viewBox="0 0 42 42">
                        <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="rgba(255,255,255,0.05)" strokeWidth="3" />
                        {(() => {
                          const catsMap = { Research: 0, Finance: 0, Legal: 0, Education: 0, Technology: 0 };
                          documents.forEach(d => { const cat = d.category || 'Technology'; if (catsMap[cat] !== undefined) catsMap[cat] += 1; else catsMap['Technology'] += 1; });
                          const total = documents.length; let accum = 0;
                          const colors = { Research: '#3b82f6', Finance: '#10b981', Legal: '#ef4444', Education: '#f59e0b', Technology: '#8b5cf6' };
                          return Object.entries(catsMap).map(([key, val]) => {
                            if (val === 0) return null;
                            const percent = (val / total) * 100;
                            const strokeDash = `${percent} ${100 - percent}`;
                            const strokeOffset = 100 - accum + 25;
                            accum += percent;
                            return <circle key={key} cx="21" cy="21" r="15.915" fill="transparent" stroke={colors[key]} strokeWidth="3" strokeDasharray={strokeDash} strokeDashoffset={strokeOffset} />;
                          });
                        })()}
                      </svg>
                      <div className="circle-legend">
                        {['Research', 'Finance', 'Legal', 'Education', 'Technology'].map((cat, i) => (
                          <div key={cat} className="legend-item">
                            <div className="legend-dot" style={{ background: ['#3b82f6', '#10b981', '#ef4444', '#f59e0b', '#8b5cf6'][i] }}></div>{cat}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <div className="glass-panel">
                <h3>Most Asked Questions</h3>
                <div style={{ marginTop: '15px' }}>
                  {analyticsData.most_asked_queries.length === 0 ? <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>No queries yet.</div> : (
                    analyticsData.most_asked_queries.map((q, idx) => {
                      const maxVal = Math.max(...analyticsData.most_asked_queries.map(i => i.cnt));
                      const percent = (q.cnt / maxVal) * 100;
                      return (
                        <div key={idx} className="bar-row">
                          <div className="bar-label-row">
                            <span style={{ maxWidth: '80%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={q.detail}>"{q.detail}"</span>
                            <span>{q.cnt}x</span>
                          </div>
                          <div className="bar-bg"><div className="bar-fill" style={{ width: `${percent}%` }}></div></div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* KNOWLEDGE GRAPH TAB */}
        {activeTab === 'graph' && (
          <div className="pane-container">
            <div>
              <h2 className="pane-title">Knowledge Graph</h2>
              <p className="pane-subtitle">Entity relationship network extracted from your documents, clustered by topic.</p>
            </div>

            <div className="glass-panel">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '20px' }}>
                <FolderDocumentPicker
                  folders={folders}
                  allDocuments={allDocuments}
                  browseFolderId={graphBrowseFolderId}
                  setBrowseFolderId={setGraphBrowseFolderId}
                  selectedDocId={graphDocId}
                  setSelectedDocId={setGraphDocId}
                  getFileIcon={getFileIcon}
                />
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn-primary" onClick={() => loadGraphData(false)} disabled={!graphDocId || graphLoading}>
                    {graphLoading ? "Mapping..." : "🕸️ Build Graph"}
                  </button>
                  <button className="btn-secondary" onClick={() => loadGraphData(true)} disabled={!graphDocId || graphLoading} title="Force a fresh extraction">
                    ↻ Regenerate
                  </button>
                </div>
              </div>

              {graphStats && (
                <div className="graph-stats-row">
                  <div className="graph-stat-card">
                    <div className="graph-stat-value">{graphStats.entities}</div>
                    <div className="graph-stat-label">Entities</div>
                  </div>
                  <div className="graph-stat-card">
                    <div className="graph-stat-value">{graphStats.relationships}</div>
                    <div className="graph-stat-label">Relationships</div>
                  </div>
                  <div className="graph-stat-card">
                    <div className="graph-stat-value">{graphStats.clusters}</div>
                    <div className="graph-stat-label">Clusters</div>
                  </div>
                  <div className="graph-stat-card">
                    <div className="graph-stat-value">{graphStats.density}</div>
                    <div className="graph-stat-label">Density</div>
                  </div>
                </div>
              )}

              <div className="graph-container" style={{ height: 'calc(100vh - 320px)', minHeight: '500px' }}>
                {graphLoading && (
                  <div style={{ position: 'absolute', top: '45%', left: '40%', color: '#00f0ff' }}>
                    Building graph...
                  </div>
                )}
                {!graphLoading && (!graphData || graphData.nodes.length === 0) ? (
                  <div style={{ textAlign: 'center', marginTop: '220px', color: '#6b7280' }}>
                    <Share2 size={30} style={{ marginBottom: '10px', opacity: 0.3 }} />
                    <p>Select a document and click Build Graph.</p>
                  </div>
                ) : (
                  <KnowledgeGraphSVG graphData={graphData} />
                )}
              </div>

              {graphData?.communities?.length > 0 && (
                <div className="graph-legend">
                  {graphData.communities.map(c => (
                    <div key={c.id} className="legend-item">
                      <div className="legend-dot" style={{ background: c.color }}></div>
                      {c.label} ({c.size})
                    </div>
                  ))}
                </div>
              )}

              {graphStats?.top_entities?.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div className="sidebar-section-title" style={{ marginBottom: '8px' }}>
                    Most Connected Entities
                  </div>
                  {graphStats.top_entities.map((e, i) => (
                    <div key={i} className="bar-row">
                      <div className="bar-label-row">
                        <span>{e.label}</span>
                        <span>{e.degree} links</span>
                      </div>
                      <div className="bar-bg">
                        <div className="bar-fill" style={{ width: `${Math.round(e.centrality * 100)}%` }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

      </div>
      {/* Global toast — lives inside dashboard-layout which is position:relative
          so fixed positioning works correctly relative to the viewport */}
      {toastMsg && (
        <div style={{
          position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)',
          background: toastType === 'success' ? 'rgba(16,185,129,0.95)' : 'rgba(239,68,68,0.95)',
          color: '#fff', padding: '12px 24px', borderRadius: '8px', fontSize: '14px',
          fontWeight: 500, zIndex: 9999, boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          maxWidth: '420px', textAlign: 'center', pointerEvents: 'none',
          animation: 'fadeIn 0.25s ease-out'
        }}>
          {toastMsg}
        </div>
      )}
    </div>
  );
}







