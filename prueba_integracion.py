import os, sqlite3
os.environ.update(DATABASE_URL="sqlite:///./prueba.db", SECRET_KEY="x"*48, CODIGO_INVITACION="invitame", ADMIN_EMAIL="admin@ejemplo.com")
from fastapi.testclient import TestClient
import main
from sqlalchemy import text
from database import engine

def chk(nombre, cond):
    print(("OK  " if cond else "FALLA"), nombre); 
    assert cond, nombre

with TestClient(main.app) as c:
    # --- salud (público) y cálculo (requiere sesión) ---
    chk("health", c.get("/").json()["status"]=="online")
    chk("cálculo set sin sesión 401", c.post("/api/partido/probabilidad-set", json={"puntos_totales_disputados":30}).status_code==401)
    # --- registro / login ---
    chk("registro sin código correcto 403", c.post("/api/auth/registro", json={"email":"a@b.co","password":"clave-larga-123","codigo_invitacion":"mal"}).status_code==403)
    chk("contraseña corta 422", c.post("/api/auth/registro", json={"email":"a@b.co","password":"corta","codigo_invitacion":"invitame"}).status_code==422)
    r=c.post("/api/auth/registro", json={"email":"Entrenador1@Ejemplo.com","password":"clave-larga-123","codigo_invitacion":"invitame"}); chk("registro entrenador", r.status_code==201 and r.json()["rol"]=="entrenador")
    chk("correo duplicado 409", c.post("/api/auth/registro", json={"email":"entrenador1@ejemplo.com","password":"clave-larga-123","codigo_invitacion":"invitame"}).status_code==409)
    r=c.post("/api/auth/registro", json={"email":"admin@ejemplo.com","password":"clave-larga-123","codigo_invitacion":"invitame"}); chk("registro admin", r.json()["rol"]=="admin")
    c.post("/api/auth/registro", json={"email":"entrenador2@ejemplo.com","password":"clave-larga-123","codigo_invitacion":"invitame"})
    chk("login incorrecto 401", c.post("/api/auth/login", data={"username":"entrenador1@ejemplo.com","password":"mala"}).status_code==401)
    chk("login usuario inexistente 401", c.post("/api/auth/login", data={"username":"nadie@ejemplo.com","password":"clave-larga-123"}).status_code==401)
    def login(e): 
        t=c.post("/api/auth/login", data={"username":e,"password":"clave-larga-123"}).json()["access_token"]; return {"Authorization":f"Bearer {t}"}
    h1,h2,ha=login("entrenador1@ejemplo.com"),login("entrenador2@ejemplo.com"),login("admin@ejemplo.com")
    chk("sin token 401", c.get("/api/tenistas").status_code==401)
    chk("token falso 401", c.get("/api/tenistas", headers={"Authorization":"Bearer xxx"}).status_code==401)
    chk("cálculo set con sesión 200", c.post("/api/partido/probabilidad-set", headers=h1, json={"puntos_totales_disputados":30}).status_code==200)
    chk("cálculo psicológico con sesión 200", c.post("/api/evaluacion/clasificar", headers=h1, json=dict(score_ansiedad_cog=3,score_ansiedad_som=3,score_autoconfianza=3,score_momentum_pos=3,score_momentum_neg=3,score_resiliencia=3,score_ctrl_emocional=3,score_foco_atencional=3,score_perseverancia=3,score_rutinas_conc=3)).status_code==200)
    chk("cálculo psicológico sin sesión 401", c.post("/api/evaluacion/clasificar", json=dict(score_ansiedad_cog=3,score_ansiedad_som=3,score_autoconfianza=3,score_momentum_pos=3,score_momentum_neg=3,score_resiliencia=3,score_ctrl_emocional=3,score_foco_atencional=3,score_perseverancia=3,score_rutinas_conc=3)).status_code==401)
    chk("/auth/yo", c.get("/api/auth/yo", headers=h1).json()["email"]=="entrenador1@ejemplo.com")
    # --- jugadores ---
    adulto=c.post("/api/tenistas", headers=h1, json={"codigo":"T01","anio_nacimiento":1998,"nivel":"Federado"}).json()
    menor=c.post("/api/tenistas", headers=h1, json={"codigo":"T02","anio_nacimiento":2010}).json()
    chk("adulto no requiere representante", adulto["requiere_representante_legal"] is False)
    chk("menor requiere representante", menor["requiere_representante_legal"] is True)
    chk("código duplicado 409", c.post("/api/tenistas", headers=h1, json={"codigo":"T01","anio_nacimiento":1998}).status_code==409)
    chk("código con espacios 422", c.post("/api/tenistas", headers=h1, json={"codigo":"Juan Perez","anio_nacimiento":1998}).status_code==422)
    P=dict(score_ansiedad_cog=2,score_ansiedad_som=2,score_autoconfianza=4.5,score_momentum_pos=4,score_momentum_neg=1.5,score_resiliencia=4.5,score_ctrl_emocional=4.5,score_foco_atencional=4.5,score_perseverancia=4.5,score_rutinas_conc=4.5)
    # --- consentimiento ---
    chk("evaluar sin consentimiento 403", c.post(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h1, json=P).status_code==403)
    chk("partido sin consentimiento 403", c.post(f"/api/tenistas/{adulto['id']}/partidos", headers=h1, json={}).status_code==403)
    chk("menor con consentimiento del jugador 422", c.post(f"/api/tenistas/{menor['id']}/consentimiento", headers=h1, json={"version_texto":"v1","otorgado_por":"jugador"}).status_code==422)
    chk("menor con representante 201", c.post(f"/api/tenistas/{menor['id']}/consentimiento", headers=h1, json={"version_texto":"v1","otorgado_por":"representante_legal"}).status_code==201)
    chk("adulto consiente 201", c.post(f"/api/tenistas/{adulto['id']}/consentimiento", headers=h1, json={"version_texto":"v1","otorgado_por":"jugador"}).status_code==201)
    chk("consentimiento duplicado 409", c.post(f"/api/tenistas/{adulto['id']}/consentimiento", headers=h1, json={"version_texto":"v1","otorgado_por":"jugador"}).status_code==409)
    # --- evaluaciones ---
    r=c.post(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h1, json=P); chk("evaluación guardada 201", r.status_code==201 and r.json()["estado_psicologico"]=="Óptimo")
    chk("evaluación fuera de rango 422", c.post(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h1, json=dict(P,score_ansiedad_cog=6)).status_code==422)
    lst=c.get(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h1).json(); chk("historial con 1 evaluación", len(lst)==1 and lst[0]["modelo_version"]=="v3")
    # --- aislamiento entre entrenadores y admin ---
    chk("otro entrenador no ve al jugador (404)", c.get(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h2).status_code==404)
    chk("otro entrenador no puede evaluar (404)", c.post(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h2, json=P).status_code==404)
    chk("otro entrenador no puede borrar (404)", c.delete(f"/api/tenistas/{adulto['id']}", headers=h2).status_code==404)
    chk("admin no lee datos psicológicos (404)", c.get(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=ha).status_code==404)
    chk("entrenador no accede a /admin (403)", c.get("/api/admin/usuarios", headers=h1).status_code==403)
    chk("admin lista usuarios", len(c.get("/api/admin/usuarios", headers=ha).json())==3)
    chk("listado propio", [t["codigo"] for t in c.get("/api/tenistas", headers=h2).json()]==[])
    # --- partidos y mediciones ---
    p=c.post(f"/api/tenistas/{adulto['id']}/partidos", headers=h1, json={"rival_codigo":"R01","torneo":"Prueba","superficie":"Arcilla"}).json()
    m=c.post(f"/api/partidos/{p['id']}/mediciones", headers=h1, json={"set_numero":1,"p1_juegos":3,"p2_juegos":2,"puntos_totales_disputados":30}); chk("medición guardada", m.status_code==201 and m.json()["nivel_confiabilidad"]=="Alta")
    chk("medición incoherente 422", c.post(f"/api/partidos/{p['id']}/mediciones", headers=h1, json={"p1_break_points_ganados":3,"p1_break_points_totales":1}).status_code==422)
    chk("otro entrenador no ve partido (404)", c.get(f"/api/partidos/{p['id']}/mediciones", headers=h2).status_code==404)
    chk("lista de mediciones", len(c.get(f"/api/partidos/{p['id']}/mediciones", headers=h1).json())==1)
    # --- revocación ---
    chk("revocar 200", c.post(f"/api/tenistas/{adulto['id']}/consentimiento/revocar", headers=h1).status_code==200)
    chk("tras revocar no guarda 403", c.post(f"/api/tenistas/{adulto['id']}/evaluaciones", headers=h1, json=P).status_code==403)
    chk("tras revocar no guarda mediciones 403", c.post(f"/api/partidos/{p['id']}/mediciones", headers=h1, json={"puntos_totales_disputados":30}).status_code==403)
    # --- supresión en cascada ---
    chk("eliminar jugador 204", c.delete(f"/api/tenistas/{adulto['id']}", headers=h1).status_code==204)
    with engine.connect() as cx:
        n=lambda t: cx.execute(text(f"select count(*) from {t}")).scalar()
        chk("cascada: sin evaluaciones", n("evaluaciones_psicologicas")==0)
        chk("cascada: sin partidos ni mediciones", n("partidos")==0 and n("mediciones_set")==0)
        chk("cascada: sin consentimientos del jugador borrado", n("consentimientos")==1)  # queda solo el del menor
    # --- desactivar usuario invalida su sesión ---
    ids={u["email"]:u["id"] for u in c.get("/api/admin/usuarios", headers=ha).json()}
    chk("admin desactiva", c.post(f"/api/admin/usuarios/{ids['entrenador2@ejemplo.com']}/desactivar", headers=ha).status_code==200)
    chk("sesión de usuario desactivado 401", c.get("/api/auth/yo", headers=h2).status_code==401)
    aud=c.get("/api/admin/auditoria", headers=ha).json()
    acciones={a["accion"] for a in aud}
    chk("auditoría registra acciones clave", {"registro","login","crear_tenista","registrar_consentimiento","crear_evaluacion","eliminar_tenista","revocar_consentimiento"}<=acciones)
print("TODO OK")
