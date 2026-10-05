"""Build data/brumadinho_locus.json: the secondary places of the Brumadinho test (ledger d5938be360254838).
The 25 municipalities, besides Brumadinho itself, that the Government of Minas Gerais lists as the "26 municipios
considerados atingidos" by the rupture of 2019-01-25 (Termo de Medidas de Reparacao, 2021-02-04, Anexos I.3/I.4).
Fixed before any SIH data were read."""
import json, unicodedata
import pegasus_data.geography as geo

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return s.replace("-", " ").replace("'", " ").strip()

SECONDARY = ["Abaeté", "Betim", "Biquinhas", "Caetanópolis", "Curvelo", "Esmeraldas", "Felixlândia", "Florestal",
             "Fortuna de Minas", "Igarapé", "Juatuba", "Maravilhas", "Mário Campos", "Mateus Leme", "Morada Nova de Minas",
             "Paineiras", "Papagaios", "Pará de Minas", "Paraopeba", "Pequi", "Pompéu", "São Gonçalo do Abaeté",
             "São Joaquim de Bicas", "São José da Varginha", "Três Marias"]
idx = {}
for c, m in geo.municipalities().items():
    idx.setdefault((norm(m["name"]), m["uf_sigla"]), []).append(m["code6"])
def code(n):
    got = idx.get((norm(n), "MG"))
    assert got and len(got) == 1, (n, got)
    return got[0]
assert code("Brumadinho") == "310900"
out = [{"name": n, "uf": "MG", "code6": code(n)} for n in SECONDARY]
assert len(out) == 25 and len({o["code6"] for o in out}) == 25
json.dump({"source": "Governo de Minas Gerais, Agencia Minas, 'Governo de Minas e instituicoes de justica abrem Consulta Popular que vai definir prioridades de investimento em Brumadinho e mais 25 municipios' (2021-10-18): 'Os 26 municipios considerados atingidos sao: ...'; also Agencia Minas 2022-12-29 'Reparacao de Brumadinho e municipios atingidos avanca...' (26 municipios)",
           "url": "https://www.agenciaminas.mg.gov.br/news/pdf/111715.pdf",
           "retrieved_from": "https://web.archive.org/web/2024/https://www.agenciaminas.mg.gov.br/news/pdf/111715.pdf (live host serves a temporary electoral-period notice, HTTP 503/302 to /comunicado, on 2026-10-05; the archived copy is the same PDF)",
           "primary": {"name": "Brumadinho", "uf": "MG", "code6": "310900"},
           "municipalities": out}, open("data/brumadinho_locus.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(len(out), [o["code6"] for o in out])
