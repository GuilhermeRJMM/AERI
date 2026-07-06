import hashlib
import hmac
import unittest

from backend.app.status_onr import assinatura_valida, componente_oficio, componentes_oficio_api, interpretar_webhook, pior_status, serializar_payload


class StatusOnrTests(unittest.TestCase):
    def test_reconhece_componentes_do_oficio(self):
        self.assertTrue(componente_oficio("API Ofício Eletrônico - Registro de Imóveis"))
        self.assertFalse(componente_oficio("CNIB"))

    def test_prioriza_interrupcao(self):
        self.assertEqual(pior_status(["OPERATIONAL", "MAJOROUTAGE"]), "MAJOROUTAGE")

    def test_le_formato_real_da_api_publica(self):
        componentes = componentes_oficio_api({"components": [
            {"id": "1", "name": "CNIB", "status": "OPERATIONAL"},
            {"id": "2", "name": "Oficio Eletronico", "status": "MAJOROUTAGE"},
            {"id": "3", "name": "API Oficio Eletrônico - Registro de Imoveis", "status": "OPERATIONAL"},
        ]})
        self.assertEqual([item["id"] for item in componentes], ["2", "3"])

    def test_valida_assinatura_instatus(self):
        payload = {"component": {"name": "Ofício Eletrônico", "status": "OPERATIONAL"}}
        segredo = "segredo-de-teste"
        corpo = serializar_payload(payload)
        assinatura = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        self.assertTrue(assinatura_valida(payload, corpo, assinatura, segredo))
        self.assertFalse(assinatura_valida(payload, corpo, "0" * 64, segredo))

    def test_interpreta_componente(self):
        evento = interpretar_webhook({
            "component_update": {"component_id": "oficio", "new_status": "MAJOROUTAGE"},
            "component": {"id": "oficio", "name": "Ofício Eletrônico"},
        })
        self.assertEqual(evento["status"], "MAJOROUTAGE")
        self.assertEqual(evento["tipo"], "COMPONENTE")

    def test_incidente_resolvido_retorna_operacional(self):
        evento = interpretar_webhook({
            "incident": {"id": "1", "name": "Ofício indisponível", "status": "RESOLVED"}
        })
        self.assertEqual(evento["status"], "OPERATIONAL")


if __name__ == "__main__":
    unittest.main()
