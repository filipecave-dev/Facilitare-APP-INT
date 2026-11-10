Attribute VB_Name = "AgendaReunioes"
'==========================================================================
' AGENDA DE REUNIÕES
' Lê o calendário do Outlook clássico (onde ficam as reuniões do Teams) e
' cria um RASCUNHO de e-mail com a tabela "AGENDA DE REUNIÃO".
' Não precisa de administrador, Azure nem conector: roda no seu Outlook.
'
' Regras de identificação:
'  - REUNIÃO (número)
'      * reunião própria (você organizou, ou o cliente te convidou)
'        -> número sequencial (guardado no seu Windows; a mesma reunião
'           sempre recebe o mesmo número, mesmo gerando de novo)
'      * agendada por colega (organizador interno) ou na sede -> 000
'  - EMPRESA
'      1) domínio do e-mail dos convidados externos, procurado na
'         biblioteca de clientes (clientes.csv)
'      2) nome/apelido de um cliente da biblioteca no assunto
'      3) se não está na biblioteca: nome tirado do domínio (ex.: @abc.com.br -> ABC)
'  - TIPO DE REUNIÃO
'      * cliente da biblioteca (base ativa) -> Manutenção
'      * cliente novo                       -> Prospecção
'  - FORMATO: link Teams/Zoom/Meet -> Virtual; só local -> Presencial;
'             link + local -> Híbrido
'==========================================================================
Option Explicit

'---------------------------- CONFIGURAÇÃO --------------------------------
' Destinatários do e-mail (separe por ";"). Pode deixar vazio e preencher no rascunho.
Private Const DESTINATARIOS As String = ""
Private Const COPIA As String = ""
Private Const ASSUNTO_EMAIL As String = "Agenda de Reuniões - atualizada em {DATA}"

' Período padrão: de hoje até hoje + N dias
Private Const DIAS_A_FRENTE As Long = 7

' Palavras que, no campo LOCAL da reunião, indicam reunião na sede da agência.
' Separe por ";". Ex.: "sede;av. paulista, 1000;sala de reunião 1"
Private Const LOCAIS_SEDE As String = "sede"

' Número usado para reunião de colega ou na sede
Private Const NUMERO_OUTROS As String = "000"

Private Const TIPO_CLIENTE_ATIVO As String = "Manutenção"
Private Const TIPO_CLIENTE_NOVO As String = "Prospecção"

' True = só entram reuniões com cliente (convidado externo ou cliente da
' biblioteca citado no assunto). False = entram todas.
Private Const SOMENTE_REUNIOES_COM_CLIENTE As Boolean = True

' Domínios que NÃO são cliente, além do domínio do seu e-mail
' (outras empresas do grupo, parceiros, fornecedores). Separe por ";".
Private Const DOMINIOS_NAO_CLIENTES As String = ""

' E-mails pessoais: contam como convidado externo, mas não viram nome de empresa
Private Const DOMINIOS_PUBLICOS As String = "gmail.com;outlook.com;outlook.com.br;hotmail.com;live.com;msn.com;yahoo.com;yahoo.com.br;icloud.com;uol.com.br;bol.com.br;terra.com.br"

' Biblioteca de clientes. Vazio = Documentos\AgendaReunioes\clientes.csv
Private Const ARQUIVO_CLIENTES As String = ""

Private Const COR_CABECALHO As String = "#008080"
'--------------------------------------------------------------------------

Private Const APP_REG As String = "AgendaReunioes"
Private Const TEXTO_VERIFICAR As String = "(verificar)"
Private Const PR_SMTP As String = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"

' Biblioteca de clientes carregada do CSV
Private mNomes() As String
Private mDominios() As String   ' "|dom1|dom2|"
Private mApelidos() As String   ' "|apelido1|apelido2|" (normalizados)
Private mQtdClientes As Long
Private mDominiosInternos As String
Private mMeuNome As String
Private mErros As Long

'==========================================================================
' MACROS PARA RODAR (Alt+F8 ou botão na barra de acesso rápido)
'==========================================================================

' Pergunta o período e cria o rascunho
Public Sub GerarRascunhoAgenda()
    Dim dtIni As Date, dtFim As Date, resp As String

    resp = InputBox("Data inicial (dd/mm/aaaa):", "Agenda de Reuniões", Format$(Date, "dd\/mm\/yyyy"))
    If Len(resp) = 0 Then Exit Sub
    If Not LerData(resp, dtIni) Then
        MsgBox "Data inválida: " & resp, vbExclamation, "Agenda de Reuniões"
        Exit Sub
    End If

    resp = InputBox("Data final (dd/mm/aaaa):", "Agenda de Reuniões", Format$(dtIni + DIAS_A_FRENTE, "dd\/mm\/yyyy"))
    If Len(resp) = 0 Then Exit Sub
    If Not LerData(resp, dtFim) Then
        MsgBox "Data inválida: " & resp, vbExclamation, "Agenda de Reuniões"
        Exit Sub
    End If
    If dtFim < dtIni Then
        MsgBox "A data final é anterior à inicial.", vbExclamation, "Agenda de Reuniões"
        Exit Sub
    End If

    Gerar dtIni, dtFim
End Sub

' Sem perguntas: de hoje até hoje + DIAS_A_FRENTE
Public Sub GerarRascunhoAgendaPadrao()
    Gerar Date, Date + DIAS_A_FRENTE
End Sub

' Define/corrige o último número sequencial usado
Public Sub AjustarUltimoNumero()
    Dim atual As String, resp As String
    atual = GetSetting(APP_REG, "Config", "UltimoNumero", "")
    resp = InputBox("Último número de reunião já usado." & vbCrLf & _
                    "A próxima reunião própria receberá este número + 1.", _
                    "Agenda de Reuniões", atual)
    If Len(resp) = 0 Then Exit Sub
    If Not IsNumeric(resp) Then
        MsgBox "Informe só números.", vbExclamation, "Agenda de Reuniões"
        Exit Sub
    End If
    SaveSetting APP_REG, "Config", "UltimoNumero", CStr(CLng(resp))
    MsgBox "Próxima reunião própria: " & Format$(CLng(resp) + 1, "000"), vbInformation, "Agenda de Reuniões"
End Sub

' Abre a biblioteca de clientes (no Excel ou no programa padrão de .csv)
Public Sub AbrirBibliotecaClientes()
    Dim caminho As String
    caminho = CaminhoClientes()
    If Not CreateObject("Scripting.FileSystemObject").FileExists(caminho) Then CriarModeloClientes caminho
    CreateObject("Shell.Application").ShellExecute caminho
End Sub

'==========================================================================
' GERAÇÃO
'==========================================================================
Private Sub Gerar(ByVal dtIni As Date, ByVal dtFim As Date)
    Dim ns As Outlook.NameSpace
    Dim itens As Outlook.Items, filtrados As Outlook.Items
    Dim obj As Object, appt As Outlook.AppointmentItem
    Dim inicio As Date, limite As Date
    Dim filtro As String, linhas As String, qtd As Long
    Dim mail As Outlook.MailItem, insp As Outlook.Inspector

    If Not CarregarClientes() Then Exit Sub
    If Not GarantirContador() Then Exit Sub

    Set ns = Application.GetNamespace("MAPI")
    mMeuNome = ns.CurrentUser.Name
    mDominiosInternos = ";" & DominioDe(MeuEmail()) & ";" & LCase$(Replace(DOMINIOS_NAO_CLIENTES, " ", "")) & ";"
    mErros = 0

    inicio = DateValue(dtIni)
    limite = DateValue(dtFim) + 1

    Set itens = ns.GetDefaultFolder(olFolderCalendar).Items
    itens.Sort "[Start]"
    itens.IncludeRecurrences = True
    filtro = "[Start] < '" & Format$(limite, "ddddd") & "' AND [End] > '" & Format$(inicio, "ddddd") & "'"
    Set filtrados = itens.Restrict(filtro)

    For Each obj In filtrados
        If TypeOf obj Is Outlook.AppointmentItem Then
            Set appt = obj
            If appt.Start >= limite Then Exit For
            If appt.Start >= inicio Then linhas = linhas & MontarLinha(appt, qtd)
        End If
    Next

    If qtd = 0 Then
        MsgBox "Nenhuma reunião encontrada entre " & Format$(inicio, "dd\/mm\/yyyy") & _
               " e " & Format$(limite - 1, "dd\/mm\/yyyy") & ".", vbInformation, "Agenda de Reuniões"
        Exit Sub
    End If

    Set mail = Application.CreateItem(olMailItem)
    With mail
        .To = DESTINATARIOS
        .CC = COPIA
        .Subject = Replace(ASSUNTO_EMAIL, "{DATA}", Format$(Date, "dd\/mm\/yyyy"))
        Set insp = .GetInspector          ' faz o Outlook inserir sua assinatura padrão
        .HTMLBody = InserirNoCorpo(.HTMLBody, MontarCorpo(linhas))
        .Save                             ' grava em Rascunhos
        .Display
    End With

    If mErros > 0 Then
        MsgBox mErros & " compromisso(s) não puderam ser lidos e ficaram de fora.", vbExclamation, "Agenda de Reuniões"
    End If
End Sub

' Devolve a linha <tr> da reunião, ou "" se ela não deve entrar
Private Function MontarLinha(ByVal appt As Outlook.AppointmentItem, ByRef qtd As Long) As String
    Dim r As Outlook.Recipient
    Dim email As String, dom As String, d As Variant
    Dim participantes As String, dominiosExt As String, empresas As String
    Dim temExterno As Boolean, clienteAtivo As Boolean, verificar As Boolean
    Dim idx As Long, emailOrg As String, organizadorInterno As Boolean
    Dim propria As Boolean, naSede As Boolean
    Dim numero As String, tipo As String, formato As String, obs As String
    Dim fisico As String, temLink As Boolean

    On Error GoTo Falha

    If DeveIgnorar(appt) Then Exit Function

    ' --- Organizador ---------------------------------------------------
    propria = (appt.MeetingStatus = olNonMeeting Or appt.MeetingStatus = olMeeting)
    If propria Then
        organizadorInterno = True
        AdicionarItem participantes, mMeuNome
    Else
        emailOrg = EmailOrganizador(appt)
        organizadorInterno = EhInterno(DominioDe(emailOrg))
        If organizadorInterno Then AdicionarItem participantes, appt.Organizer
    End If

    ' --- Convidados ----------------------------------------------------
    For Each r In appt.Recipients
        If r.Type <> olResource Then
            email = SmtpDoDestinatario(r)
            dom = DominioDe(email)
            If EhInterno(dom) Then
                AdicionarItem participantes, r.Name
            Else
                temExterno = True
                AdicionarItem dominiosExt, dom
            End If
        End If
    Next
    If Len(participantes) = 0 Then participantes = mMeuNome

    ' --- Empresa / tipo ------------------------------------------------
    ' 1) domínio dos convidados na biblioteca
    For Each d In Split(dominiosExt, ";")
        idx = ClientePorDominio(CStr(d))
        If idx >= 0 Then AdicionarItem empresas, mNomes(idx)
    Next
    ' 2) cliente da biblioteca citado no assunto
    If Len(empresas) = 0 Then
        idx = ClientePorAssunto(appt.Subject)
        If idx >= 0 Then empresas = mNomes(idx)
    End If
    clienteAtivo = (Len(empresas) > 0)

    ' 3) cliente novo: nome pelo domínio
    If Not clienteAtivo And temExterno Then
        For Each d In Split(dominiosExt, ";")
            If Len(d) > 0 And Not EhPublico(CStr(d)) Then AdicionarItem empresas, NomePeloDominio(CStr(d))
        Next
        If Len(empresas) = 0 Then
            empresas = TEXTO_VERIFICAR
            verificar = True
        End If
    End If

    If Not clienteAtivo And Not temExterno Then
        If SOMENTE_REUNIOES_COM_CLIENTE Then Exit Function   ' reunião interna
    End If

    If clienteAtivo Then
        tipo = TIPO_CLIENTE_ATIVO
    ElseIf temExterno Then
        tipo = TIPO_CLIENTE_NOVO
    End If

    ' --- Local / formato -----------------------------------------------
    fisico = LocalFisico(appt.Location)
    naSede = EhSede(appt.Location)
    temLink = TemLinkOnline(appt)
    If temLink And Len(fisico) = 0 Then
        formato = "Virtual"
    ElseIf temLink Then
        formato = "Híbrido"
    ElseIf Len(fisico) > 0 Then
        formato = "Presencial"
    Else
        formato = "A definir"
    End If

    ' --- Número --------------------------------------------------------
    If naSede Then
        numero = NUMERO_OUTROS                    ' reunião na sede da agência
    ElseIf propria Or Not organizadorInterno Then
        numero = NumeroSequencial(appt)           ' sua, ou o cliente te convidou
    Else
        numero = NUMERO_OUTROS                    ' agendada por colega
    End If

    ' --- Observação ----------------------------------------------------
    If formato = "Presencial" Or formato = "Híbrido" Then obs = fisico
    If verificar Then
        If Len(obs) > 0 Then obs = obs & " | "
        obs = obs & "Assunto: " & appt.Subject
    End If

    qtd = qtd + 1
    MontarLinha = "<tr>" & _
        Celula(numero, False) & _
        Celula(Replace(participantes, ";", ", "), True) & _
        Celula(Replace(empresas, ";", " / "), False) & _
        Celula(Format$(appt.Start, "dd\/mm"), False) & _
        Celula(Format$(appt.Start, "hh\:nn"), False) & _
        Celula(formato, False) & _
        Celula(tipo, False) & _
        Celula(obs, False) & "</tr>"
    Exit Function

Falha:
    mErros = mErros + 1
    Debug.Print "Agenda de Reuniões - compromisso ignorado: " & Err.Description
    MontarLinha = ""
End Function

Private Function DeveIgnorar(ByVal appt As Outlook.AppointmentItem) As Boolean
    Dim s As String
    If appt.AllDayEvent Then DeveIgnorar = True: Exit Function
    If appt.MeetingStatus = olMeetingCanceled Or appt.MeetingStatus = olMeetingReceivedAndCanceled Then DeveIgnorar = True: Exit Function
    If appt.ResponseStatus = olResponseDeclined Then DeveIgnorar = True: Exit Function
    s = Normalizar(appt.Subject)
    If Left$(s, 9) = "cancelado" Or Left$(s, 9) = "cancelada" Or Left$(s, 8) = "canceled" Or Left$(s, 9) = "cancelled" Then DeveIgnorar = True
End Function

'==========================================================================
' HTML DO E-MAIL
'==========================================================================
Private Function MontarCorpo(ByVal linhas As String) As String
    Dim h As String
    h = "<div style=""font-family:Aptos,Calibri,Arial,sans-serif;font-size:11pt;color:#000000"">"
    h = h & "<p style=""margin:0 0 12pt 0"">Prezados, " & Saudacao() & "</p>"
    h = h & "<p style=""margin:0 0 12pt 0"">Segue a agenda atualizada.</p>"
    h = h & "<table border=""1"" cellpadding=""0"" cellspacing=""0"" width=""100%"" " & _
            "style=""border-collapse:collapse;width:100%;border:1px solid #000000"">"
    h = h & "<tr><td colspan=""8"" bgcolor=""" & COR_CABECALHO & """ style=""" & EstiloCabecalho("18pt") & """>AGENDA DE REUNIÃO</td></tr>"
    h = h & "<tr>" & _
        Cabecalho("REUNIÃO", 8) & _
        Cabecalho("GERENTE DE CONTAS /<br>PARTICIPANTES", 18) & _
        Cabecalho("EMPRESA", 17) & _
        Cabecalho("DATA", 9) & _
        Cabecalho("HORÁRIO", 8) & _
        Cabecalho("FORMATO DA<br>REUNIÃO", 10) & _
        Cabecalho("TIPO DE REUNIÃO", 12) & _
        Cabecalho("OBSERVAÇÃO", 18) & "</tr>"
    h = h & linhas
    h = h & "</table>"
    h = h & "<p style=""margin:12pt 0 0 0"">Att.</p>"
    h = h & "</div>"
    MontarCorpo = h
End Function

Private Function EstiloCabecalho(ByVal respiro As String) As String
    EstiloCabecalho = "background:" & COR_CABECALHO & ";color:#FFFFFF;" & _
        "font-family:'Times New Roman',Times,serif;font-size:10.5pt;font-weight:bold;" & _
        "text-align:center;vertical-align:middle;border:1px solid #000000;" & _
        "padding:" & respiro & " 6px"
End Function

Private Function Cabecalho(ByVal texto As String, ByVal largura As Long) As String
    Cabecalho = "<td width=""" & largura & "%"" bgcolor=""" & COR_CABECALHO & """ style=""" & _
                EstiloCabecalho("14pt") & """>" & texto & "</td>"
End Function

Private Function Celula(ByVal texto As String, ByVal serifada As Boolean) As String
    Dim fonte As String
    If serifada Then
        fonte = "font-family:'Times New Roman',Times,serif;font-size:11pt;"
    Else
        fonte = "font-family:Aptos,Calibri,Arial,sans-serif;font-size:12pt;"
    End If
    Celula = "<td style=""" & fonte & "text-align:center;vertical-align:top;" & _
             "border:1px solid #000000;padding:2px 6px 18px 6px"">" & Esc(texto) & "</td>"
End Function

Private Function Saudacao() As String
    Select Case Hour(Now)
        Case Is < 12: Saudacao = "bom dia"
        Case Is < 18: Saudacao = "boa tarde"
        Case Else:    Saudacao = "boa noite"
    End Select
End Function

' Coloca o conteúdo logo após <body>, mantendo a assinatura abaixo
Private Function InserirNoCorpo(ByVal htmlAtual As String, ByVal conteudo As String) As String
    Dim p1 As Long, p2 As Long
    p1 = InStr(1, htmlAtual, "<body", vbTextCompare)
    If p1 > 0 Then p2 = InStr(p1, htmlAtual, ">")
    If p2 > 0 Then
        InserirNoCorpo = Left$(htmlAtual, p2) & conteudo & Mid$(htmlAtual, p2 + 1)
    Else
        InserirNoCorpo = conteudo & htmlAtual
    End If
End Function

Private Function Esc(ByVal s As String) As String
    s = Replace(s, "&", "&amp;")
    s = Replace(s, "<", "&lt;")
    s = Replace(s, ">", "&gt;")
    s = Replace(s, """", "&quot;")
    Esc = s
End Function

'==========================================================================
' NUMERAÇÃO SEQUENCIAL
'==========================================================================
Private Function GarantirContador() As Boolean
    Dim resp As String
    If Len(GetSetting(APP_REG, "Config", "UltimoNumero", "")) > 0 Then
        GarantirContador = True
        Exit Function
    End If
    resp = InputBox("Primeira execução." & vbCrLf & vbCrLf & _
                    "Qual foi o ÚLTIMO número de reunião já usado?" & vbCrLf & _
                    "(ex.: 126 -> a próxima reunião própria será 127)", "Agenda de Reuniões", "0")
    If Len(resp) = 0 Or Not IsNumeric(resp) Then Exit Function
    SaveSetting APP_REG, "Config", "UltimoNumero", CStr(CLng(resp))
    GarantirContador = True
End Function

' A mesma reunião recebe sempre o mesmo número
Private Function NumeroSequencial(ByVal appt As Outlook.AppointmentItem) As String
    Dim chave As String, n As String, ultimo As Long
    chave = ChaveReuniao(appt)
    n = GetSetting(APP_REG, "Numeros", chave, "")
    If Len(n) = 0 Then
        ultimo = CLng(GetSetting(APP_REG, "Config", "UltimoNumero", "0")) + 1
        n = Format$(ultimo, "000")
        SaveSetting APP_REG, "Config", "UltimoNumero", CStr(ultimo)
        SaveSetting APP_REG, "Numeros", chave, n
    End If
    NumeroSequencial = n
End Function

Private Function ChaveReuniao(ByVal appt As Outlook.AppointmentItem) As String
    Dim id As String
    On Error Resume Next
    id = appt.GlobalAppointmentID
    If Len(id) = 0 Then id = appt.EntryID
    On Error GoTo 0
    If appt.IsRecurring Then id = id & "_" & Format$(appt.Start, "yyyymmdd")
    ChaveReuniao = id
End Function

'==========================================================================
' BIBLIOTECA DE CLIENTES (clientes.csv)
' Colunas: EMPRESA ; DOMINIOS ; PALAVRAS NO ASSUNTO
'  - DOMINIOS e PALAVRAS: vários separados por vírgula
'  - o próprio nome da EMPRESA também é procurado no assunto
'==========================================================================
Private Function CaminhoClientes() As String
    Dim docs As String
    If Len(ARQUIVO_CLIENTES) > 0 Then
        CaminhoClientes = ARQUIVO_CLIENTES
        Exit Function
    End If
    On Error Resume Next
    docs = CreateObject("WScript.Shell").SpecialFolders("MyDocuments")
    On Error GoTo 0
    If Len(docs) = 0 Then docs = Environ$("USERPROFILE") & "\Documents"
    CaminhoClientes = docs & "\AgendaReunioes\clientes.csv"
End Function

Private Sub CriarModeloClientes(ByVal caminho As String)
    Dim fso As Object, pasta As String, st As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    pasta = fso.GetParentFolderName(caminho)
    If Not fso.FolderExists(pasta) Then fso.CreateFolder pasta
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2
    st.Charset = "utf-8"
    st.Open
    st.WriteText "EMPRESA;DOMINIOS;PALAVRAS NO ASSUNTO" & vbCrLf & "TPL;;TPL" & vbCrLf
    st.SaveToFile caminho, 2
    st.Close
End Sub

Private Function CarregarClientes() As Boolean
    Dim caminho As String, texto As String, linhas() As String, campos() As String
    Dim i As Long, sep As String, nome As String, parte As Variant, item As String

    caminho = CaminhoClientes()
    If Not CreateObject("Scripting.FileSystemObject").FileExists(caminho) Then
        CriarModeloClientes caminho
        MsgBox "Criei a biblioteca de clientes em:" & vbCrLf & caminho & vbCrLf & vbCrLf & _
               "Cadastre os clientes da base ativa (abre no Excel), salve e rode a macro de novo.", _
               vbInformation, "Agenda de Reuniões"
        CreateObject("Shell.Application").ShellExecute caminho
        Exit Function
    End If

    texto = LerTexto(caminho)
    texto = Replace(texto, vbCrLf, vbLf)
    texto = Replace(texto, vbCr, vbLf)
    linhas = Split(texto, vbLf)

    mQtdClientes = 0
    ReDim mNomes(0 To UBound(linhas) + 1)
    ReDim mDominios(0 To UBound(linhas) + 1)
    ReDim mApelidos(0 To UBound(linhas) + 1)

    sep = ";"
    If InStr(linhas(0), ";") = 0 And InStr(linhas(0), ",") > 0 Then sep = ","

    For i = 0 To UBound(linhas)
        If Len(Trim$(Replace(linhas(i), sep, ""))) > 0 Then
            campos = Split(linhas(i) & sep & sep, sep)
            nome = Trim$(Replace(campos(0), """", ""))
            If Len(nome) > 0 And UCase$(nome) <> "EMPRESA" And Left$(nome, 1) <> "#" Then
                mNomes(mQtdClientes) = nome

                mDominios(mQtdClientes) = "|"
                For Each parte In Split(Replace(Replace(campos(1), """", ""), " ", ","), ",")
                    item = LCase$(Trim$(parte))
                    If Left$(item, 1) = "@" Then item = Mid$(item, 2)
                    If Left$(item, 4) = "www." Then item = Mid$(item, 5)
                    If Len(item) > 0 Then mDominios(mQtdClientes) = mDominios(mQtdClientes) & item & "|"
                Next

                mApelidos(mQtdClientes) = "|" & Normalizar(nome) & "|"
                For Each parte In Split(Replace(campos(2), """", ""), ",")
                    item = Normalizar(CStr(parte))
                    If Len(item) > 0 Then mApelidos(mQtdClientes) = mApelidos(mQtdClientes) & item & "|"
                Next

                mQtdClientes = mQtdClientes + 1
            End If
        End If
    Next
    CarregarClientes = True
End Function

Private Function ClientePorDominio(ByVal dom As String) As Long
    Dim i As Long, d As Variant
    ClientePorDominio = -1
    If Len(dom) = 0 Then Exit Function
    For i = 0 To mQtdClientes - 1
        For Each d In Split(mDominios(i), "|")
            If Len(d) > 0 Then
                If dom = d Or Right$(dom, Len(d) + 1) = "." & d Then
                    ClientePorDominio = i
                    Exit Function
                End If
            End If
        Next
    Next
End Function

Private Function ClientePorAssunto(ByVal assunto As String) As Long
    Dim i As Long, a As Variant, s As String
    ClientePorAssunto = -1
    s = " " & Normalizar(assunto) & " "
    For i = 0 To mQtdClientes - 1
        For Each a In Split(mApelidos(i), "|")
            If Len(a) > 0 Then
                If InStr(s, " " & a & " ") > 0 Then
                    ClientePorAssunto = i
                    Exit Function
                End If
            End If
        Next
    Next
End Function

' Lê UTF-8 (com ou sem BOM) ou ANSI (padrão do Excel "CSV separado por vírgulas")
Private Function LerTexto(ByVal caminho As String) As String
    Dim st As Object, b() As Byte, charset As String, t As String
    Set st = CreateObject("ADODB.Stream")
    st.Type = 1
    st.Open
    st.LoadFromFile caminho
    If st.Size > 0 Then b = st.Read
    st.Close

    If EhUtf8Valido(b) Then charset = "utf-8" Else charset = "windows-1252"

    Set st = CreateObject("ADODB.Stream")
    st.Type = 2
    st.Charset = charset
    st.Open
    st.LoadFromFile caminho
    t = st.ReadText(-1)
    st.Close
    If Left$(t, 1) = ChrW$(&HFEFF) Then t = Mid$(t, 2)
    LerTexto = t
End Function

Private Function EhUtf8Valido(ByRef b() As Byte) As Boolean
    Dim i As Long, n As Long, k As Long, c As Long
    On Error GoTo Vazio
    n = UBound(b)
    On Error GoTo 0
    i = 0
    Do While i <= n
        c = b(i)
        If c < &H80 Then
            k = 0
        ElseIf c >= &HC2 And c <= &HDF Then
            k = 1
        ElseIf c >= &HE0 And c <= &HEF Then
            k = 2
        ElseIf c >= &HF0 And c <= &HF4 Then
            k = 3
        Else
            Exit Function
        End If
        Do While k > 0
            i = i + 1
            If i > n Then Exit Function
            If b(i) < &H80 Or b(i) > &HBF Then Exit Function
            k = k - 1
        Loop
        i = i + 1
    Loop
    EhUtf8Valido = True
    Exit Function
Vazio:
    EhUtf8Valido = True
End Function

'==========================================================================
' E-MAILS E DOMÍNIOS
'==========================================================================
Private Function MeuEmail() As String
    Dim s As String
    On Error Resume Next
    s = SmtpDeEntrada(Application.Session.CurrentUser.AddressEntry)
    If InStr(s, "@") = 0 Then s = Application.Session.Accounts.Item(1).SmtpAddress
    MeuEmail = LCase$(s)
End Function

Private Function EmailOrganizador(ByVal appt As Outlook.AppointmentItem) As String
    Dim ae As Outlook.AddressEntry
    On Error Resume Next
    Set ae = appt.GetOrganizer
    If Not ae Is Nothing Then EmailOrganizador = SmtpDeEntrada(ae)
End Function

Private Function SmtpDoDestinatario(ByVal r As Outlook.Recipient) As String
    Dim s As String
    On Error Resume Next
    s = r.PropertyAccessor.GetProperty(PR_SMTP)
    If InStr(s, "@") = 0 Then s = SmtpDeEntrada(r.AddressEntry)
    If InStr(s, "@") = 0 Then s = r.Address
    SmtpDoDestinatario = LCase$(Trim$(s))
End Function

Private Function SmtpDeEntrada(ByVal ae As Outlook.AddressEntry) As String
    Dim s As String
    On Error Resume Next
    If ae Is Nothing Then Exit Function
    If ae.AddressEntryUserType = olExchangeUserAddressEntry Or _
       ae.AddressEntryUserType = olExchangeRemoteUserAddressEntry Then
        s = ae.GetExchangeUser.PrimarySmtpAddress
    End If
    If InStr(s, "@") = 0 Then s = ae.PropertyAccessor.GetProperty(PR_SMTP)
    If InStr(s, "@") = 0 Then s = ae.Address
    SmtpDeEntrada = LCase$(Trim$(s))
End Function

Private Function DominioDe(ByVal email As String) As String
    Dim p As Long
    p = InStrRev(email, "@")
    If p > 0 Then DominioDe = LCase$(Trim$(Mid$(email, p + 1)))
End Function

' Sem domínio (contato interno do Exchange) também conta como interno
Private Function EhInterno(ByVal dom As String) As Boolean
    Dim d As Variant
    If Len(dom) = 0 Then EhInterno = True: Exit Function
    For Each d In Split(mDominiosInternos, ";")
        If Len(d) > 0 Then
            If dom = d Or Right$(dom, Len(d) + 1) = "." & d Then EhInterno = True: Exit Function
        End If
    Next
End Function

Private Function EhPublico(ByVal dom As String) As Boolean
    EhPublico = InStr(";" & DOMINIOS_PUBLICOS & ";", ";" & dom & ";") > 0
End Function

' abc.com.br -> ABC ; mail.empresa-x.com -> EMPRESA-X
Private Function NomePeloDominio(ByVal dom As String) As String
    Dim partes() As String, i As Long
    partes = Split(dom, ".")
    i = 0
    If UBound(partes) >= 2 Then
        If partes(0) = "mail" Or partes(0) = "email" Or partes(0) = "corp" Then i = 1
    End If
    NomePeloDominio = UCase$(partes(i))
End Function

'==========================================================================
' LOCAL / FORMATO
'==========================================================================
Private Function TemLinkOnline(ByVal appt As Outlook.AppointmentItem) As Boolean
    Dim t As String
    On Error Resume Next
    t = LCase$(appt.Location & " " & appt.Body)
    TemLinkOnline = InStr(t, "teams.microsoft.com") > 0 Or InStr(t, "microsoft teams") > 0 Or _
                    InStr(t, "zoom.us/") > 0 Or InStr(t, "meet.google.com") > 0 Or _
                    InStr(t, "webex.com") > 0
End Function

' Local sem os textos automáticos do Teams e sem links
Private Function LocalFisico(ByVal loc As String) As String
    Dim parte As Variant, item As String, r As String
    loc = Replace(loc, "Reunião do Microsoft Teams", "", 1, -1, vbTextCompare)
    loc = Replace(loc, "Microsoft Teams Meeting", "", 1, -1, vbTextCompare)
    loc = Replace(loc, "Reunião do Teams", "", 1, -1, vbTextCompare)
    loc = Replace(loc, "Microsoft Teams", "", 1, -1, vbTextCompare)
    For Each parte In Split(loc, ";")
        item = Trim$(parte)
        If Len(item) > 0 And InStr(1, item, "http", vbTextCompare) = 0 Then
            If Len(r) > 0 Then r = r & "; "
            r = r & item
        End If
    Next
    LocalFisico = r
End Function

Private Function EhSede(ByVal loc As String) As Boolean
    Dim k As Variant, s As String
    s = " " & Normalizar(loc) & " "
    For Each k In Split(LOCAIS_SEDE, ";")
        If Len(Normalizar(CStr(k))) > 0 Then
            If InStr(s, " " & Normalizar(CStr(k)) & " ") > 0 Then EhSede = True: Exit Function
        End If
    Next
End Function

'==========================================================================
' UTILITÁRIOS
'==========================================================================
' minúsculas, sem acento, só letras/números separados por um espaço
Private Function Normalizar(ByVal s As String) As String
    Const DE As String = "áàâãäéèêëíìîïóòôõöúùûüçñ"
    Const PARA As String = "aaaaaeeeeiiiiooooouuuucn"
    Dim i As Long, c As String, p As Long, r As String
    s = LCase$(s)
    For i = 1 To Len(s)
        c = Mid$(s, i, 1)
        p = InStr(1, DE, c, vbBinaryCompare)
        If p > 0 Then c = Mid$(PARA, p, 1)
        If (c >= "a" And c <= "z") Or (c >= "0" And c <= "9") Then
            r = r & c
        Else
            r = r & " "
        End If
    Next
    Do While InStr(r, "  ") > 0
        r = Replace(r, "  ", " ")
    Loop
    Normalizar = Trim$(r)
End Function

' Acrescenta item numa lista "a;b;c" sem repetir
Private Sub AdicionarItem(ByRef lista As String, ByVal item As String)
    item = Trim$(Replace(item, ";", ","))
    If Len(item) = 0 Then Exit Sub
    If InStr(1, ";" & lista & ";", ";" & item & ";", vbTextCompare) > 0 Then Exit Sub
    If Len(lista) > 0 Then lista = lista & ";"
    lista = lista & item
End Sub

Private Function LerData(ByVal s As String, ByRef d As Date) As Boolean
    Dim p() As String, dia As Long, mes As Long, ano As Long
    s = Replace(Replace(Trim$(s), "-", "/"), ".", "/")
    p = Split(s, "/")
    If UBound(p) < 1 Or UBound(p) > 2 Then Exit Function
    If Not IsNumeric(p(0)) Or Not IsNumeric(p(1)) Then Exit Function
    dia = CLng(p(0)): mes = CLng(p(1))
    If UBound(p) = 2 Then
        If Not IsNumeric(p(2)) Then Exit Function
        ano = CLng(p(2))
        If ano < 100 Then ano = ano + 2000
    Else
        ano = Year(Date)
    End If
    If mes < 1 Or mes > 12 Or dia < 1 Or dia > 31 Then Exit Function
    d = DateSerial(ano, mes, dia)
    LerData = (Day(d) = dia)
End Function
