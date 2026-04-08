const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const chatLog = document.getElementById("chat-log");
const welcome = document.getElementById("welcome");
const historyList = document.getElementById("history-list");
const sidebar = document.getElementById("sidebar");
const authScreen = document.getElementById("auth-screen");
const authForm = document.getElementById("auth-form");
const authStudentId = document.getElementById("auth-student-id");
const authPassword = document.getElementById("auth-password");
const authDisplayName = document.getElementById("auth-display-name");
const authSubmit = document.getElementById("auth-submit");
const authSwitch = document.getElementById("auth-switch");
const authError = document.getElementById("auth-error");
const logoutBtn = document.getElementById("logout-btn");
const topbarUser = document.getElementById("topbar-user");
const STORAGE_KEY = "ukm_ftsm_chat_v3";
const THEME_KEY = "ukm_ftsm_theme";
const MAX_HISTORY = 20;

let chatHistory = [];
let conversationId = null;
let busy = false;
let currentStudent = null;
let authMode = "login";

// Knowledge base management is now handled on /manage.

