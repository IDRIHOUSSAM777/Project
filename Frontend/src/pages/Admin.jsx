import { useState, useEffect } from 'react';
import api from '../services/api';
import { useI18n } from '../i18n';

const Admin = () => {
  const { t, locale } = useI18n();
  const [alertes, setAlertes] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/admin/alertes').then(res => setAlertes(res.data))
       .catch(err => setError(err.response?.status === 403 ? t('admin.forbidden') : t('admin.error')));
  }, [t]);

  const resolve = async (id) => {
      if(!window.confirm(t('admin.resolveConfirm'))) return;
      try {
        await api.put(`/admin/alertes/${id}/resolve`, { nouveau_statut_objet: "Disponible" });
        setAlertes(alertes.filter(a => a.id_alerte !== id));
      } catch {
        setError(t('admin.error'));
      }
  };

  return (
    <main className="page-pad">
      <div className="container">
        <section className="card admin">
          <h1 className="section-title">{t('admin.title')}</h1>
          <p className="subtitle">{t('admin.subtitle')}</p>

          <div className="tags">
            <span className="pill" style={{color:'var(--primary)', borderColor:'var(--primary)'}}><i className="fa-solid fa-bell"></i> {alertes.length} {t('admin.alerts')}</span>
            <span className="pill"><i className="fa-solid fa-users"></i> {t('admin.users')}</span>
          </div>

          <div style={{marginTop:'20px', display:'flex', flexDirection:'column', gap:'12px'}}>
              {error && <div className="chip chip-busy">{error}</div>}
              {alertes.length === 0 && !error && <div className="chip chip-done">{t('admin.noAlerts')}</div>}
              
              {alertes.map(a => (
                  <div key={a.id_alerte} className="row">
                      <div className="row-left">
                          <div className="ico" style={{background:'#fef3f2', color:'var(--danger)'}}><i className="fa-solid fa-triangle-exclamation"></i></div>
                          <div>
                              <div className="title">{a.message}</div>
                              <div className="sub">{a.nom_objet} • {new Intl.DateTimeFormat(locale).format(new Date(a.date_alerte))}</div>
                          </div>
                      </div>
                      <button className="btn" onClick={()=>resolve(a.id_alerte)}>{t('admin.resolve')}</button>
                  </div>
              ))}
          </div>
        </section>
      </div>
    </main>
  );
};
export default Admin;
