"""Build data/rio_doce_locus.json: the 41 municipalities of the IBAMA Laudo Tecnico Preliminar (Nov 2015, sec. 2.4 table,
'lista de 41 municipios afetados a partir de Mariana-MG ate a foz do Rio Doce, em Linhares-ES'), with IBGE 6-digit codes.
Fixed before any SIH data were read."""
import json, unicodedata
import pegasus_data.geography as geo

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return s.replace("-", " ").replace("'", " ").replace("  ", " ").strip()

MG = ["Acaiaca","Aimorés","Alpercata","Barra Longa","Belo Oriente","Bom Jesus do Galho","Bugre","Caratinga","Conselheiro Pena",
 "Córrego Novo","Dionísio","Fernandes Tourinho","Galiléia","Governador Valadares","Iapu","Ipaba","Ipatinga","Itueta","Mariana",
 "Marliéria","Naque","Periquito","Pingo-d'Água","Ponte Nova","Raul Soares","Resplendor","Rio Doce","Santa Cruz do Escalvado",
 "Santana do Paraíso","São Domingos do Prata","São José do Goiabal","São Pedro dos Ferros","Sem-Peixe","Sobrália","Timóteo",
 "Tumiritinga","Rio Casca"]
ES = ["Baixo Guandu","Colatina","Linhares","Marilândia"]
idx = {}
for c, m in geo.municipalities().items():
    idx.setdefault((norm(m["name"]), m["uf_sigla"]), []).append(str(c).zfill(7)[:6] if len(str(c)) >= 7 else str(c).zfill(6))
out = []
for uf, names in (("MG", MG), ("ES", ES)):
    for n in names:
        k = (norm(n), uf)
        alt = {"galileia": "galileia"}.get(k[0], k[0])
        got = idx.get((alt, uf))
        assert got and len(got) == 1, (n, uf, got)
        out.append({"name": n, "uf": uf, "code6": got[0]})
assert len(out) == 41
json.dump({"source": "IBAMA, Laudo Tecnico Preliminar, Impactos ambientais decorrentes do desastre envolvendo o rompimento da barragem de Fundao, Nov 2015, sec. 2.4 table (41 municipios)",
           "url": "https://www.ibama.gov.br/phocadownload/noticias/noticias2015/laudo_tecnico_preliminar_Ibama.pdf",
           "municipalities": out}, open("data/rio_doce_locus.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(len(out), [o["code6"] for o in out])
