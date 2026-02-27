import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../services/api';
import { useI18n } from '../i18n';

const parseBackendDate = (value) => {
  if (!value) return null;
  const raw = String(value);
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(raw);
  const parsed = new Date(hasTimezone ? raw : `${raw}Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
};

const notificationTypeLabel = (type, language) => {
  const normalized = String(type || '').toUpperCase();
  if (normalized === 'TURN_READY') {
    if (language === 'en') return 'Your turn';
    if (language === 'es') return 'Tu turno';
    if (language === 'ar') return 'حان دورك';
    return 'Votre tour';
  }
  if (normalized === 'RESERVATION') {
    if (language === 'en') return 'Reservation';
    if (language === 'es') return 'Reserva';
    if (language === 'ar') return 'حجز';
    return 'Réservation';
  }
  if (normalized === 'ALERT') {
    if (language === 'en') return 'Alert';
    if (language === 'es') return 'Alerta';
    if (language === 'ar') return 'تنبيه';
    return 'Alerte';
  }
  if (language === 'ar') return 'معلومة';
  return 'Info';
};

const formatRelativeTime = (value, language) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return '';

  const diffMs = Date.now() - parsed.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (language === 'en') {
    if (diffMs < minute) return 'just now';
    if (diffMs < hour) return `${Math.floor(diffMs / minute)} min ago`;
    if (diffMs < day) return `${Math.floor(diffMs / hour)} h ago`;
    return `${Math.floor(diffMs / day)} d ago`;
  }

  if (language === 'es') {
    if (diffMs < minute) return 'ahora';
    if (diffMs < hour) return `hace ${Math.floor(diffMs / minute)} min`;
    if (diffMs < day) return `hace ${Math.floor(diffMs / hour)} h`;
    return `hace ${Math.floor(diffMs / day)} d`;
  }

  if (language === 'ar') {
    if (diffMs < minute) return 'الآن';
    if (diffMs < hour) return `منذ ${Math.floor(diffMs / minute)} دقيقة`;
    if (diffMs < day) return `منذ ${Math.floor(diffMs / hour)} ساعة`;
    return `منذ ${Math.floor(diffMs / day)} يوم`;
  }

  if (diffMs < minute) return "à l'instant";
  if (diffMs < hour) return `il y a ${Math.floor(diffMs / minute)} min`;
  if (diffMs < day) return `il y a ${Math.floor(diffMs / hour)} h`;
  return `il y a ${Math.floor(diffMs / day)} j`;
};

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { language, t, translateData } = useI18n();

  const [user, setUser] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const [notifLoading, setNotifLoading] = useState(false);
  const notifRef = useRef(null);
  const token = localStorage.getItem('access_token');

  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    setNotifLoading(true);
    try {
      const res = await api.get('/users/me/notifications?limit=12');
      const items = Array.isArray(res?.data?.items) ? res.data.items : [];
      const unread = Number(res?.data?.unread_count);
      setNotifications(items);
      setUnreadCount(Number.isFinite(unread) ? unread : 0);
    } catch {
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setNotifLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api.get('/users/me')
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem('access_token');
        setNotifications([]);
        setUnreadCount(0);
        navigate('/login');
      });
  }, [token, navigate]);

  useEffect(() => {
    if (!token) return undefined;
    fetchNotifications();
    const timer = window.setInterval(fetchNotifications, 30000);
    return () => window.clearInterval(timer);
  }, [token, fetchNotifications]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isNotifOpen && notifRef.current && !notifRef.current.contains(event.target)) {
        setIsNotifOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isNotifOpen]);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setIsDarkMode(true);
      return;
    }
    if (savedTheme === 'light') {
      setIsDarkMode(false);
      return;
    }
    const prefersDark = typeof window !== 'undefined'
      && window.matchMedia
      && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setIsDarkMode(prefersDark);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDarkMode);
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  if (!token || ['/login', '/signup'].includes(location.pathname)) return null;

  const isActive = (paths) => {
    const list = Array.isArray(paths) ? paths : [paths];
    return list.some((path) => {
      if (path === '/') return location.pathname === '/';
      return location.pathname === path || location.pathname.startsWith(`${path}/`);
    }) ? 'active' : '';
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setNotifications([]);
    setUnreadCount(0);
    navigate('/login');
  };

  const handleToggleNotifications = async () => {
    const nextOpen = !isNotifOpen;
    setIsNotifOpen(nextOpen);
    if (nextOpen) await fetchNotifications();
  };

  const handleOpenNotification = async (notification) => {
    if (!notification) return;
    if (!notification.est_lu) {
      try {
        const res = await api.post(`/users/me/notifications/${notification.id_notification}/read`);
        const unread = Number(res?.data?.unread_count);
        setUnreadCount(Number.isFinite(unread) ? unread : 0);
        setNotifications((prev) =>
          prev.map((item) =>
            item.id_notification === notification.id_notification
              ? { ...item, est_lu: true }
              : item
          )
        );
      } catch {
        // keep UI usable
      }
    }
    if (notification.id_objet) {
      setIsNotifOpen(false);
      navigate(`/equipment/${notification.id_objet}`);
    }
  };

  const handleMarkAllNotificationsRead = async () => {
    try {
      await api.post('/users/me/notifications/read-all');
      setUnreadCount(0);
      setNotifications((prev) => prev.map((item) => ({ ...item, est_lu: true })));
    } catch {
      // ignore
    }
  };

  const firstName = user?.prenom || '';
  const lastName = user?.nom || '';
  const fullName = `${firstName} ${lastName}`.trim() || translateData('role', 'Utilisateur');
  const roleLabel = translateData('role', user?.role || 'Utilisateur');
  const initials = `${firstName[0] || ''}${lastName[0] || ''}`.toUpperCase() || 'U';

  return (
    <header className="topbar">
      <div className="brand">
        <button className="icon-btn" aria-label={t('nav.search')} onClick={() => navigate('/search')}>
          <i className="fa-solid fa-magnifying-glass" />
        </button>
        <div className="logo">
          <span className="logo-strong">SMART</span>
          <span className="logo-soft">FIND</span>
        </div>
      </div>

      <nav className="nav">
        <Link className={`nav-item ${isActive('/')}`} to="/">
          <i className="fa-solid fa-house" />
          <span>{t('nav.home')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/carte')}`} to="/carte">
          <i className="fa-solid fa-map" />
          <span>{t('nav.map')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/categories')}`} to="/categories">
          <i className="fa-solid fa-table-cells-large" />
          <span>{t('nav.categories')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/history')}`} to="/history">
          <i className="fa-regular fa-clock" />
          <span>{t('nav.history')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/profile')}`} to="/profile">
          <i className="fa-regular fa-user" />
          <span>{t('nav.profile')}</span>
        </Link>
        {String(user?.role || '').toLowerCase() === 'admin' && (
          <Link className={`nav-item ${isActive(['/admin/alerts', '/admin/inventory'])}`} to="/admin/alerts">
            <i className="fa-solid fa-shield-halved" />
            <span>{t('nav.admin')}</span>
          </Link>
        )}
      </nav>

      <div className="userbox">
        <div className="usertext">
          <div className="username">{fullName}</div>
          <div className="role">{roleLabel}</div>
        </div>

        <button
          className="icon-btn mode-btn"
          onClick={() => setIsDarkMode((prev) => !prev)}
          aria-label={isDarkMode ? t('nav.switchToLight') : t('nav.switchToDark')}
          title={isDarkMode ? t('nav.modeLight') : t('nav.modeDark')}
        >
          <i className={`fa-solid ${isDarkMode ? 'fa-sun' : 'fa-moon'}`} />
        </button>

        <div className="notif-wrap" ref={notifRef}>
          <button
            className={`icon-btn notif-btn ${isNotifOpen ? 'open' : ''}`}
            onClick={handleToggleNotifications}
            aria-label={t('nav.notifications')}
            title={t('nav.notifications')}
          >
            <i className="fa-regular fa-bell" />
            {unreadCount > 0 && <span className="notif-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
          </button>

          {isNotifOpen && (
            <div className="notif-pop card">
              <div className="notif-head">
                <strong>{t('nav.notifications')}</strong>
                {unreadCount > 0 && (
                  <button type="button" className="notif-read-all" onClick={handleMarkAllNotificationsRead}>
                    {t('nav.markAllRead')}
                  </button>
                )}
              </div>

              <div className="notif-body">
                {notifLoading && notifications.length === 0 && <div className="notif-empty">{t('nav.loading')}</div>}
                {!notifLoading && notifications.length === 0 && <div className="notif-empty">{t('nav.noNotifications')}</div>}
                {notifications.map((notification) => (
                  <button
                    type="button"
                    key={notification.id_notification}
                    className={`notif-item ${notification.est_lu ? '' : 'unread'}`}
                    onClick={() => handleOpenNotification(notification)}
                  >
                    <div className="notif-item-top">
                      <span className="notif-type">{notificationTypeLabel(notification.type_notification, language)}</span>
                      <span className="notif-time">{formatRelativeTime(notification.date_notification, language)}</span>
                    </div>
                    <span className="notif-message">{notification.message}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="avatar" onClick={() => navigate('/profile')} title={t('nav.myProfile')}>
          {initials}
        </div>

        <button className="icon-btn" onClick={handleLogout} aria-label={t('nav.logout')} title={t('nav.logout')}>
          <i className="fa-solid fa-right-from-bracket" />
        </button>
      </div>
    </header>
  );
};

export default Navbar;
