"""Sistema de Envio (Mac) — envio de lâminas de prospecção por SMTP.

Versão para macOS do Disparo de Lâminas (Windows). Envia direto pelo
servidor de e-mail do subdomínio de prospecção (SMTP):

- a campanha escolhida define a lâmina (imagem) e a mensagem usadas;
- a lista de envio é lida de uma planilha (xlsx/xlsm/csv);
- e-mails duplicados na base ou já enviados anteriormente são apontados;
- limite diário (padrão 80) e intervalo entre envios (padrão 3 minutos);
- cópia (CC) escolhida contato a contato antes do disparo;
- todo envio fica registrado na lista de **Enviados** (histórico em SQLite).
"""

# Versão do programa: aparece no título da janela, no nome do pacote (zip) e em
# cada envio registrado. Suba a cada entrega e descreva em HISTORICO_VERSOES.md.
__version__ = "1.0.0"
