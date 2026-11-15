/*
 * Motor de detección y sustitución de datos personales (contexto español).
 * Funciona íntegramente en local: no realiza ninguna petición de red.
 */
(function (global) {
  'use strict';

  // ---------------------------------------------------------------- utilidades
  const L = 'A-Za-zÁÉÍÓÚÜÑáéíóúüñÀÈÌÒÙàèìòùÇçÏï';
  const UP = 'A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇÏ';
  const LOW = 'a-záéíóúüñàèìòùçï';
  const strip = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '');
  const norm = (s) => strip(s).toLowerCase();
  const isUpperWord = (s) => /\p{L}/u.test(s) && s === s.toUpperCase();
  const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&');

  // ---------------------------------------------------------- diccionarios
  const NOMBRES_M = `Aarón Abel Adolfo Adrián Agustín Alberto Alejandro Alfonso Alfredo Álvaro Amador Andrés Ángel Aníbal Antonio Armando Arturo Benito Bernardo Borja Bruno Carlos César Cipriano Claudio Cristian Cristóbal Daniel David Diego Domingo Eduardo Elías Emilio Enrique Ernesto Esteban Eugenio Fabián Federico Felipe Félix Fermín Fernando Francisco Gabriel Gerardo Germán Gilberto Gonzalo Gregorio Guillermo Gustavo Héctor Hugo Ignacio Iker Isaac Ismael Iván Jacinto Jaime Javier Jesús Joan Joaquín Joel Jordi Jorge José Josep Juan Julián Julio Lázaro Leandro Leonardo Lorenzo Lucas Luciano Luis Manuel Marc Marcelino Marcos Mariano Mario Martín Mateo Matías Mauricio Maximino Miguel Mohamed Moisés Nicolás Óscar Pablo Pascual Pau Pedro Rafael Ramiro Ramón Raúl Ricardo Roberto Rodrigo Rogelio Rubén Salvador Samuel Santiago Saúl Sebastián Sergio Simón Teodoro Tomás Ulises Valentín Vicente Víctor Xavier Xabier Yago`;
  const NOMBRES_F = `Adela Adriana Águeda Aitana Alba Alejandra Alicia Almudena Amalia Amparo Ana Andrea Ángela Ángeles Anna Antonia Araceli Ariadna Asunción Aurora Beatriz Begoña Belén Blanca Camila Candela Carla Carlota Carmen Carolina Catalina Celia Clara Claudia Concepción Consuelo Cristina Daniela Diana Dolores Elena Elisa Elvira Emilia Encarnación Esperanza Estefanía Ester Esther Eva Fátima Gabriela Gema Gemma Gloria Graciela Guadalupe Inés Inmaculada Irene Isabel Jimena Josefa Juana Julia Laia Laura Leire Lidia Lorena Lucía Luisa Lourdes Magdalena Maite Manuela Marina Marta María Mariana Marisa Mercedes Milagros Miriam Mónica Montserrat Natalia Nerea Noelia Nuria Olga Paloma Paola Patricia Paula Pilar Raquel Rebeca Remedios Rocío Rosa Rosario Rut Sandra Sara Silvia Sofía Soledad Sonia Susana Teresa Valeria Vanesa Verónica Victoria Virginia Yolanda Zoe`;
  const APELLIDOS = `Aguilar Alonso Álvarez Arias Benítez Blanco Bravo Caballero Calvo Campos Cano Carmona Carrasco Castillo Castro Cortés Crespo Cruz Delgado Díaz Diez Domínguez Durán Esteban Fernández Ferrer Flores Fuentes Gallardo Gallego García Garrido Gil Giménez Gómez González Guerrero Gutiérrez Guzmán Hernández Herrera Herrero Hidalgo Ibáñez Iglesias Jiménez León Lorenzo López Lozano Marín Márquez Martín Martínez Medina Méndez Molina Montero Mora Morales Moreno Muñoz Navarro Nieto Núñez Ortega Ortiz Pascual Pastor Peña Pérez Prieto Ramírez Ramos Reyes Rodríguez Román Romero Rubio Ruiz Sáez Sánchez Santana Santiago Santos Sanz Serrano Soler Suárez Torres Vargas Vázquez Vega Velasco Vicente Vidal`;
  const toSet = (s) => new Set(s.split(/\s+/).filter(Boolean).map(norm));
  const SET_M = toSet(NOMBRES_M);
  const SET_F = toSet(NOMBRES_F);
  const SET_AP = toSet(APELLIDOS);
  const isGiven = (t) => SET_M.has(norm(t)) || SET_F.has(norm(t));

  // Palabras que nunca forman parte de un nombre propio de persona.
  const STOP = new Set(`a al ante bajo con contra de del desde durante e el en entre frente hacia hasta la las lo los mediante o para por que se según sin sobre su sus tras un una y
    mayor edad vecino vecina vecinos domicilio domiciliado domiciliada provisto provista titular dni nie nif cif pasaporte nombre representación representante calle avenida plaza número nº
    demandante demandado demandada demandados recurrente recurrido recurrida actor actora parte partes ejecutante ejecutado ejecutada denunciante denunciado denunciada querellante querellado querellada acusado acusada investigado investigada perjudicado perjudicada testigo
    juez jueza magistrado magistrada magistrados presidente presidenta fiscal fiscalía letrado letrada letrados secretario secretaria abogado abogada abogados procurador procuradora procuradores director directora notario notaria registrador registradora ministro ministra alcalde alcaldesa consejero consejera gerente administrador administradora perito perita doctor doctora
    juzgado tribunal audiencia sala sección ley código real decreto artículo art constitución estado gobierno ayuntamiento comunidad administración ministerio agencia tesorería seguridad social instituto nacional provincial superior supremo constitucional primera primero segunda segundo tercera tercero
    enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre lunes martes miércoles jueves viernes sábado domingo
    madrid barcelona valencia sevilla zaragoza málaga murcia palma bilbao alicante córdoba valladolid vigo gijón granada coruña vitoria elche oviedo badajoz cartagena salamanca burgos albacete castellón santander pamplona logroño toledo cádiz huelva jaén león lleida tarragona girona almería cáceres ourense lugo pontevedra segovia soria teruel zamora ávila cuenca guadalajara huesca palencia ciudad españa
    sr sra srta don doña excmo excma ilmo ilma señor señora usted ss sª
    otrosí otrosi digo suplico expone solicita hechos fundamentos derecho fallo antecedentes primero único resultando considerando
    compostela benz guardia civil policía
    s.l s.a s.l.u s.coop sl sa slu`.split(/\s+/).filter(Boolean).map(norm));

  const PARTICLES = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'i', 'da', 'dos']);

  // ---------------------------------------------------------- categorías
  const CATEGORIES = [
    { id: 'persona', label: 'Nombres de personas', on: true },
    { id: 'empresa', label: 'Nombres de empresas (S.L., S.A.…)', on: true },
    { id: 'dni', label: 'DNI / NIF', on: true },
    { id: 'nie', label: 'NIE', on: true },
    { id: 'cif', label: 'CIF', on: true },
    { id: 'pasaporte', label: 'Pasaporte', on: true },
    { id: 'email', label: 'Correos electrónicos', on: true },
    { id: 'telefono', label: 'Teléfonos', on: true },
    { id: 'iban', label: 'IBAN / cuentas bancarias', on: true },
    { id: 'tarjeta', label: 'Tarjetas bancarias', on: true },
    { id: 'nss', label: 'Nº Seguridad Social', on: true },
    { id: 'direccion', label: 'Direcciones postales', on: true },
    { id: 'cp', label: 'Códigos postales', on: true },
    { id: 'matricula', label: 'Matrículas de vehículos', on: true },
    { id: 'ip', label: 'Direcciones IP', on: true },
    { id: 'nacimiento', label: 'Fechas de nacimiento', on: true },
    { id: 'fecha', label: 'Todas las fechas', on: false },
    { id: 'procedimiento', label: 'Nº de procedimiento / autos', on: false },
    { id: 'manual', label: 'Añadidos manualmente', on: true },
    { id: 'custom', label: 'Términos personalizados', on: true },
  ];
  const CAT_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.label]));

  // ---------------------------------------------------------- validaciones
  const DNI_LETTERS = 'TRWAGMYFPDXBNJZSQVHLCKE';
  const dniLetter = (num) => DNI_LETTERS[Number(num) % 23];
  function validDni(s) {
    const m = s.replace(/[\s.\-]/g, '').toUpperCase().match(/^(\d{8})([A-Z])$/);
    return !!m && dniLetter(m[1]) === m[2];
  }
  function validNie(s) {
    const m = s.replace(/[\s.\-]/g, '').toUpperCase().match(/^([XYZ])(\d{7})([A-Z])$/);
    if (!m) return false;
    return dniLetter('XYZ'.indexOf(m[1]) + m[2]) === m[3];
  }
  function luhn(num) {
    const d = num.replace(/\D/g, '');
    let sum = 0, alt = false;
    for (let i = d.length - 1; i >= 0; i--) {
      let n = +d[i];
      if (alt) { n *= 2; if (n > 9) n -= 9; }
      sum += n; alt = !alt;
    }
    return sum % 10 === 0;
  }

  // ---------------------------------------------------------- detectores
  // Cada detector devuelve [{start, end, text, type, meta}]
  const W = `[${L}]`;
  const NB = `(?<![${L}0-9])`; // no precedido de letra/dígito
  const NA = `(?![${L}0-9])`; // no seguido de letra/dígito

  function regexFinder(type, re, opts = {}) {
    return (text) => {
      const out = [];
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text))) {
        const g = opts.group || 0;
        const val = m[g];
        if (!val) continue;
        if (opts.valid && !opts.valid(val, m)) continue;
        const start = m.index + (g ? m[0].indexOf(val) : 0);
        out.push({ start, end: start + val.length, text: val, type });
        if (m[0].length === 0) re.lastIndex++;
      }
      return out;
    };
  }

  const FINDERS = {
    email: regexFinder('email', /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g),
    iban: regexFinder('iban', /\b[A-Z]{2}\d{2}(?:[ \-]?[A-Z0-9]{4}){4,7}(?:[ \-]?[A-Z0-9]{1,3})?\b/g, {
      valid: (v) => { const c = v.replace(/[ \-]/g, ''); return c.length >= 15 && c.length <= 34 && /^(ES\d{22}|[A-Z]{2}\d{2}[A-Z0-9]{11,30})$/.test(c); },
    }),
    ccc: regexFinder('iban', /\b\d{4}[ \-]\d{4}[ \-]\d{2}[ \-]\d{10}\b/g),
    tarjeta: regexFinder('tarjeta', /\b(?:\d{4}[ \-]?){3}\d{1,4}\b/g, { valid: (v) => { const d = v.replace(/\D/g, ''); return d.length >= 13 && d.length <= 16 && luhn(d); } }),
    dni: regexFinder('dni', new RegExp(`${NB}\\d{1,2}\\.?\\d{3}\\.?\\d{3}[ \\-]?[A-Za-z]${NA}`, 'g'), {
      valid: (v) => { const c = v.replace(/[\s.\-]/g, ''); return c.length === 9 && validDni(c); },
    }),
    dniContext: regexFinder('dni', new RegExp(`(?:D\\.?N\\.?I\\.?|N\\.?I\\.?F\\.?)(?:\\s*(?:n[º°o.]|núm\\.?|número))?\\s*[:.]?\\s*(\\d{1,2}\\.?\\d{3}\\.?\\d{3}[ \\-]?[A-Za-z]?)${NA}`, 'gi'), { group: 1 }),
    nie: regexFinder('nie', new RegExp(`${NB}[XYZxyz][ \\-]?\\d{7}[ \\-]?[A-Za-z]${NA}`, 'g'), { valid: (v) => validNie(v) }),
    nieContext: regexFinder('nie', new RegExp(`N\\.?I\\.?E\\.?\\s*(?:n[º°o.]\\s*)?[:.]?\\s*([XYZxyz][ \\-]?\\d{7}[ \\-]?[A-Za-z]?)${NA}`, 'gi'), { group: 1 }),
    cif: regexFinder('cif', new RegExp(`${NB}[ABCDEFGHJNPQRSUVW][ \\-]?\\d{7}[0-9A-J]${NA}`, 'g'), {
      valid: (v, m) => true,
    }),
    pasaporte: regexFinder('pasaporte', /pasaporte(?:\s*(?:n[º°o.]|núm\.?|número))?\s*[:.]?\s*([A-Z]{2,3}\d{6,7}|[A-Z0-9]{6,9})\b/gi, { group: 1 }),
    nss: regexFinder('nss', /(?:afiliaci[oó]n|seguridad social|N\.?A\.?F\.?|N\.?U\.?S\.?S\.?|NSS)[^\d\n]{0,25}(\d{2}[\/ \-]?\d{8}[\/ \-]?\d{2})\b/gi, { group: 1 }),
    telefono: regexFinder('telefono', new RegExp(`${NB}(?:(?:\\+|00)\\s?34[\\s.\\-]?)?[6789]\\d{2}(?:[\\s.\\-]?\\d{2,3}){2,3}${NA}`, 'g'), {
      valid: (v) => { const d = v.replace(/\D/g, '').replace(/^(0034|34)(?=\d{9}$)/, ''); return d.length === 9; },
    }),
    telefonoInt: regexFinder('telefono', /(?:\+|00)(?!34)\d{1,3}[\s.\-]?\(?\d{1,4}\)?(?:[\s.\-]?\d{2,4}){2,4}\b/g),
    ip: regexFinder('ip', /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g),
    matricula: regexFinder('matricula', new RegExp(`${NB}(?:\\d{4}[ \\-]?[BCDFGHJKLMNPRSTVWXYZ]{3}|[A-Z]{1,2}[ \\-]?\\d{4}[ \\-]?[A-Z]{1,2})${NA}`, 'g'), {
      valid: (v) => !/^(?:[A-Z]{1,2})[ \-]?\d{4}[ \-]?(?:[A-Z]{1,2})$/.test(v) || /^(?:A|AB|AL|AV|B|BA|BI|BU|C|CA|CC|CE|CO|CR|CS|CU|GC|GE|GI|GR|GU|H|HU|IB|J|L|LE|LO|LU|M|MA|ML|MU|NA|O|OR|OU|P|PM|PO|S|SA|SE|SG|SO|SS|T|TE|TF|TO|V|VA|VI|Z|ZA)[ \-]?\d{4}/.test(v),
    }),
    cp: regexFinder('cp', /(?:C\.\s?P\.|\bCP\b|c[oó]digo postal)\s*[:.]?\s*((?:0[1-9]|[1-4]\d|5[0-2])\d{3})\b/gi, { group: 1 }),
    cpCiudad: regexFinder('cp', new RegExp(`${NB}((?:0[1-9]|[1-4]\\d|5[0-2])\\d{3})(?=\\s*[\\-–,]?\\s*(?:\\(?[${UP}][${LOW}]+))(?!\\s*(?:euros?|€|eur\\b|ptas|pesetas|metros|m2|km|horas|días|meses|años|unidades|personas))`, 'g'), { group: 1 }),
    direccion: regexFinder('direccion', new RegExp(
      `(?<![${L}])(?:C\\/|Calle|C\\.|Avda\\.?|Av\\.|Avenida|Pza\\.?|Plaza|Pl\\.|P[º°o]\\.?|Paseo|Camino|Cmno\\.|Ctra\\.?|Carretera|Ronda|Rda\\.|Travesía|Trav\\.|Urb\\.|Urbanización|Glorieta|Callejón|Rambla|Vía|Bulevar|Pasaje|Polígono|Pol\\.|Partida|Barrio|Lugar|Cuesta|Costanilla|Carrer|Rúa|Kalea)` +
      `\\s+(?:(?:de|del|de la|de los|de las|dels|d')\\s*)?[${UP}0-9][${L}0-9.'ºª\\-]*(?:\\s+(?:de|del|la|las|los|el|y|i|[${UP}0-9][${L}0-9.'ºª\\-]*)){0,7}` +
      `(?:\\s*,?\\s*(?:(?:n[º°o.]?|núm\\.?|número)\\s*)?(?:\\d{1,4}(?![0-9])(?:[A-Za-z](?![A-Za-z]))?|s\\/n))?(?:(?:\\s*[,\\-]\\s*(?:\\d{1,2}(?![0-9])\\s*[º°ª]?\\s*(?:(?:izq(?:uierda)?|izda|dcha|der(?:echa)?|[A-Za-z]{1,2})\\.?(?![A-Za-z]))?|(?:bajo|bj|pral|ático|esc\\.?\\s*\\w+|portal\\s*\\w+|piso\\s*\\w+|puerta\\s*\\w+|planta\\s*\\w+|local\\s*\\w+)))*)?`,
      'g'), { valid: (v) => v.length > 6 && /\s/.test(v) }),
    nacimiento: regexFinder('nacimiento', /(?:nacid[oa]|naci[oó]|fecha de nacimiento|f\.\s?nac\.?|nacimiento)[^\d\n]{0,20}(\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4}|\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4})/gi, { group: 1 }),
    fecha: regexFinder('fecha', /\b(?:\d{1,2}[\/.\-]\d{1,2}[\/.\-](?:19|20)\d{2}|\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|sept?iembre|octubre|noviembre|diciembre)\s+(?:de|del)\s+\d{4})\b/gi),
    procedimiento: regexFinder('procedimiento', /(?:autos|procedimiento|proc\.|recurso|rollo|expediente|exp\.|ejecutoria|diligencias(?: previas)?|D\.P\.|P\.O\.|P\.A\.|juicio (?:verbal|ordinario|monitorio|cambiario)|J\.V\.|N\.I\.G\.?|NIG)[^\d\n]{0,30}(\d{1,7}\s?\/\s?\d{2,4}(?:\s?[\-–]\s?[A-Z0-9]+)?|\d{5}\s?\d{2}\s?\d\s?\d{4}\s?\d{7})/gi, { group: 1 }),
  };

  // ---------------------------------------------- nombres de persona y empresa
  const CAP = `(?:[${UP}][${LOW}]+(?:[\\-'][${UP}]?[${LOW}]+)?|[${UP}]{2,}(?:[\\-'][${UP}]+)?|[${UP}]\\.)`;
  const SP = '[ \\t\\u00a0]+';
  const NAME_SEQ = `${CAP}(?:${SP}(?:(?:de|del|de la|de las|de los|y|i)${SP})?${CAP}){0,5}`;
  const HONOR = `(?:D\\.ª|Dª|D\\.\\s?ª|Dña\\.?|Doña|DOÑA|Don|DON|D\\.|Sr\\.|Sra\\.|Srta\\.|SR\\.|SRA\\.|Señor|Señora|SEÑOR|SEÑORA|Excmo\\.\\s*Sr\\.|Excma\\.\\s*Sra\\.|Ilmo\\.\\s*Sr\\.|Ilma\\.\\s*Sra\\.)`;
  const FEMALE_HONOR = /^(D\.ª|Dª|D\. ?ª|Dña|Doña|DOÑA|Sra|SRA|Srta|Señora|SEÑORA|Excma|Ilma)/;

  function cleanNameTokens(seq) {
    // Divide en palabras, corta en la primera palabra vacía y elimina partículas finales.
    const parts = seq.split(/\s+/);
    const out = [];
    for (const p of parts) {
      const n = norm(p.replace(/\.$/, ''));
      if (STOP.has(n) && !PARTICLES.has(n)) break;
      if (/^[A-ZÁÉÍÓÚÑ]\.$/.test(p) && out.length) break; // inicial suelta al final
      out.push(p);
    }
    while (out.length && PARTICLES.has(norm(out[out.length - 1]))) out.pop();
    return out;
  }

  function findPersons(text) {
    const out = [];
    const add = (start, tokens, honor) => {
      if (!tokens.length) return;
      const real = tokens.filter((t) => !PARTICLES.has(norm(t)));
      if (!real.length) return;
      if (real.every((t) => /^[A-ZÁÉÍÓÚÑ]\.$/.test(t))) return;
      const str = tokens.join(' ');
      // Reconstruye el texto exacto tal y como aparece (los espacios pueden variar).
      const re = new RegExp(tokens.map(escRe).join('[ \\t\\u00a0]+'), 'y');
      re.lastIndex = start;
      const m = re.exec(text);
      if (!m) return;
      out.push({ start, end: start + m[0].length, text: m[0], type: 'persona', meta: { female: honor ? FEMALE_HONOR.test(honor) : undefined, honor: !!honor } });
      void str;
    };

    // 1) Tras tratamiento: D., Dña., Sr., Sra., Don, Doña…
    const reH = new RegExp(`(?<![${L}])(${HONOR})[ \\t\\u00a0]*(${NAME_SEQ})`, 'g');
    let m;
    while ((m = reH.exec(text))) {
      const seqStart = m.index + m[0].length - m[2].length;
      const tokens = cleanNameTokens(m[2]);
      if (tokens.length && !STOP.has(norm(tokens[0]))) add(seqStart, tokens, m[1]);
    }

    // 2) Secuencias de palabras en mayúscula que empiezan por un nombre conocido o contienen dos apellidos conocidos.
    const reS = new RegExp(`(?<![${L}])(${NAME_SEQ})`, 'g');
    while ((m = reS.exec(text))) {
      let tokens = m[1].split(/\s+/);
      // Recortar palabras vacías al principio (p. ej. "Contra Juan Pérez").
      let offset = m.index;
      while (tokens.length && (STOP.has(norm(tokens[0].replace(/\.$/, ''))) || PARTICLES.has(norm(tokens[0])) || /^[A-ZÁÉÍÓÚÑ]\.$/.test(tokens[0]))) {
        const t = tokens.shift();
        offset = text.indexOf(tokens[0] ?? '', offset + t.length);
      }
      tokens = cleanNameTokens(tokens.join(' '));
      // Si el primer término no es un nombre conocido pero hay uno después («Caso de Elena Ruiz»), empezar en él.
      const gi = tokens.findIndex((t) => isGiven(t));
      if (gi > 0 && !isGiven(tokens[0])) {
        const skipped = tokens.slice(0, gi);
        for (const t of skipped) offset = text.indexOf(t, offset) + t.length;
        offset = text.indexOf(tokens[gi], offset);
        tokens = tokens.slice(gi);
      }
      const real = tokens.filter((t) => !PARTICLES.has(norm(t)));
      if (real.length < 2) continue;
      const firstGiven = isGiven(real[0]);
      const surnames = real.filter((t) => SET_AP.has(norm(t))).length;
      if (firstGiven || surnames >= 2 || (surnames >= 1 && real.some((t) => isGiven(t)))) {
        add(offset, tokens, null);
      }
    }
    return out;
  }

  function findCompanies(text) {
    const out = [];
    const re = new RegExp(`(?<![${L}])((?:[${UP}0-9][${L}0-9&'\\-]*\\.?)(?:[ \\t\\u00a0]+(?:(?:de|del|la|las|los|y|e|&|i)[ \\t\\u00a0]+)?(?:[${UP}0-9][${L}0-9&'\\-]*\\.?)){0,6})[ \\t\\u00a0]*,?[ \\t\\u00a0]*(S\\.?\\s?L\\.?\\s?U\\.?|S\\.?\\s?L\\.?\\s?N\\.?\\s?E\\.?|S\\.?\\s?L\\.?|S\\.?\\s?A\\.?\\s?U\\.?|S\\.?\\s?A\\.?|S\\.?\\s?Coop\\.?(?:\\s?And\\.?|\\s?V\\.?)?|S\\.?\\s?C\\.?|C\\.?\\s?B\\.?|S\\.?\\s?A\\.?\\s?T\\.?|A\\.?\\s?I\\.?\\s?E\\.?|Sociedad Limitada|Sociedad Anónima)(?![${L}])`, 'g');
    let m;
    while ((m = re.exec(text))) {
      let tokens = m[1].split(/\s+/);
      while (tokens.length > 1 && STOP.has(norm(tokens[0].replace(/\.$/, '')))) tokens.shift();
      if (!tokens.length || STOP.has(norm(tokens[0]))) continue;
      const name = tokens.join(' ');
      const start = text.indexOf(name, m.index);
      const end = m.index + m[0].length;
      if (start < 0) continue;
      out.push({ start, end, text: text.slice(start, end), type: 'empresa', meta: { suffix: m[2] } });
    }
    return out;
  }

  // ------------------------------------------------------- generador de ficticios
  const GIVEN_M = ['Fulano', 'Mengano', 'Zutano', 'Perengano', 'Ficticiano', 'Inventado', 'Supuestino', 'Anónimo'];
  const GIVEN_F = ['Fulana', 'Mengana', 'Zutana', 'Perengana', 'Ficticiana', 'Inventada', 'Supuestina', 'Anónima'];
  const SURN = ['de Tal', 'Ejemplo', 'Ficción', 'Prueba', 'Inventiva', 'Supuesto', 'Muestra', 'Simulacro', 'Maqueta', 'Hipótesis', 'Ensayo', 'Quimera', 'Fantasía', 'Figuración', 'Apariencia', 'Conjetura', 'Borrador', 'Ilusión', 'Ficticio', 'Invención'];
  const GREEK = ['Alfa', 'Beta', 'Gamma', 'Delta', 'Épsilon', 'Zeta', 'Eta', 'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Ómicron', 'Pi', 'Rho', 'Sigma', 'Tau', 'Ípsilon', 'Fi', 'Ji', 'Psi', 'Omega'];
  const ROMAN = ['', ' II', ' III', ' IV', ' V', ' VI', ' VII', ' VIII', ' IX', ' X'];
  const pick = (pool, i) => pool[i % pool.length] + (ROMAN[Math.floor(i / pool.length)] ?? ' ' + (Math.floor(i / pool.length) + 1));
  const pad = (n, w) => String(n).padStart(w, '0');

  class Faker {
    constructor(style) {
      this.style = style || 'ficticio';
      this.maps = new Map(); // tipo -> Map(clave normalizada -> sustituto)
      this.counters = {};
      this.given = new Map();
      this.surn = new Map();
    }
    next(type) { return (this.counters[type] = (this.counters[type] || 0) + 1); }
    keyFor(type, text) {
      if (type === 'persona' || type === 'empresa' || type === 'direccion' || type === 'manual' || type === 'custom') return norm(text).replace(/\s+/g, ' ').trim();
      return text.replace(/[^A-Za-z0-9@.]/g, '').toUpperCase();
    }
    fake(type, text, meta = {}) {
      if (!this.maps.has(type)) this.maps.set(type, new Map());
      const map = this.maps.get(type);
      const key = this.keyFor(type, text);
      if (map.has(key)) return map.get(key);
      const v = this.style === 'etiqueta' ? this.label(type, text, meta) : this.make(type, text, meta);
      map.set(key, v);
      return v;
    }
    label(type, text, meta) {
      if (type === 'persona') return `[PERSONA ${this.personTag(text)}]`;
      const names = { empresa: 'EMPRESA', dni: 'DNI', nie: 'NIE', cif: 'CIF', pasaporte: 'PASAPORTE', email: 'EMAIL', telefono: 'TELÉFONO', iban: 'CUENTA', tarjeta: 'TARJETA', nss: 'NSS', direccion: 'DIRECCIÓN', cp: 'CP', matricula: 'MATRÍCULA', ip: 'IP', nacimiento: 'FECHA NACIMIENTO', fecha: 'FECHA', procedimiento: 'PROCEDIMIENTO', manual: 'DATO', custom: 'DATO' };
      return `[${names[type] || 'DATO'} ${this.next('lbl_' + type)}]`;
    }
    personTag(text) {
      // Etiquetas consistentes por apellido principal / nombre completo.
      const k = this.personKey(text);
      if (!this._ptag) this._ptag = new Map();
      if (!this._ptag.has(k)) {
        const i = this._ptag.size;
        this._ptag.set(k, i < 26 ? String.fromCharCode(65 + i) : 'A' + (i - 25));
      }
      return this._ptag.get(k);
    }
    personKey(text) {
      const real = text.split(/\s+/).filter((t) => !PARTICLES.has(norm(t)));
      const sur = real.filter((t) => !isGiven(t));
      return norm((sur[0] || real[real.length - 1] || text));
    }
    givenFor(tok, female) {
      const k = norm(tok) + (female ? '|f' : '|m');
      if (!this.given.has(k)) {
        const n = [...this.given.keys()].filter((x) => x.endsWith(female ? '|f' : '|m')).length;
        this.given.set(k, pick(female ? GIVEN_F : GIVEN_M, n));
      }
      return this.given.get(k);
    }
    surnFor(tok) {
      const k = norm(tok);
      if (!this.surn.has(k)) this.surn.set(k, pick(SURN, this.surn.size));
      return this.surn.get(k);
    }
    make(type, text, meta) {
      const n = () => this.next(type);
      switch (type) {
        case 'persona': return this.person(text, meta);
        case 'empresa': {
          const suffix = (meta.suffix || (text.match(/(S\.?\s?L\.?\s?U\.?|S\.?\s?L\.?|S\.?\s?A\.?\s?U\.?|S\.?\s?A\.?|S\.?\s?Coop\.?)\s*$/) || [])[1] || '').trim();
          return `Empresa Ficticia ${pick(GREEK, n() - 1)}${suffix ? ', ' + suffix : ''}`;
        }
        case 'dni': { const num = pad(n(), 8); return num + dniLetter(num); }
        case 'nie': { const num = pad(n(), 7); return 'X' + num + dniLetter(num); }
        case 'cif': return (text.trim()[0] || 'B').toUpperCase() + pad(n(), 8);
        case 'pasaporte': return 'XXX' + pad(n(), 6);
        case 'email': return `persona.ficticia${n()}@ejemplo.invalid`;
        case 'telefono': { const i = n(); const plus = /^\s*(\+|00)/.test(text) ? '+34 ' : ''; return `${plus}000 000 ${pad(i, 3)}`; }
        case 'iban': { const i = pad(n(), 4); return /^[A-Z]{2}/i.test(text.trim()) ? `ES00 0000 0000 0000 0000 ${i}` : `0000 0000 00 000000${i}`; }
        case 'tarjeta': return `0000 0000 0000 ${pad(n(), 4)}`;
        case 'nss': return `00/${pad(n(), 8)}/00`;
        case 'direccion': return `Calle Ficticia ${pick(GREEK, n() - 1)}, n.º 0`;
        case 'cp': return '00000';
        case 'matricula': return `${pad(n(), 4)} FIC`;
        case 'ip': return `192.0.2.${n() % 255}`;
        case 'nacimiento': case 'fecha': { const i = n(); return `${pad(((i - 1) % 28) + 1, 2)}/01/1900`; }
        case 'procedimiento': return `${pad(n(), 4)}/0000`;
        default: return `Dato Ficticio ${pick(GREEK, n() - 1)}`;
      }
    }
    person(text, meta) { return this.personParts(text, meta).join(' '); }
    personParts(text, meta = {}) {
      const toks = text.split(/\s+/).filter((t) => !PARTICLES.has(norm(t)) && !/^[A-ZÁÉÍÓÚÑ]\.$/.test(t));
      if (!toks.length) return [pick(GIVEN_M, 0)];
      let female = meta.female;
      if (female === undefined) female = SET_F.has(norm(toks[0])) && !SET_M.has(norm(toks[0]));
      const out = [];
      if (toks.length === 1) {
        // Un solo término: nombre de pila si es conocido; si no, apellido.
        out.push(isGiven(toks[0]) && !meta.honor ? this.givenFor(toks[0], female) : this.surnFor(toks[0]));
      } else {
        let i = 0;
        const g0 = isGiven(toks[0]);
        if (g0 || toks.length >= 2) { out.push(this.givenFor(toks[0], female)); i = 1; }
        // Nombre compuesto (José Luis, María José…)
        if (toks.length >= 3 && isGiven(toks[1]) && !SET_AP.has(norm(toks[1]))) { out.push(this.givenFor(toks[1], female)); i = 2; }
        for (; i < toks.length; i++) out.push(this.surnFor(toks[i]));
      }
      return out;
    }
  }

  // ---------------------------------------------------------------- análisis
  /**
   * Analiza el texto y devuelve entidades únicas:
   * [{id, type, text, replacement, count, enabled}]
   */
  function analyze(text, options) {
    const opt = Object.assign({ categories: {}, style: 'ficticio', custom: [], extraEntities: [] }, options);
    const enabled = (t) => opt.categories[t] !== false && (opt.categories[t] ?? CATEGORIES.find((c) => c.id === t)?.on);
    const found = [];
    const run = (name, type) => { if (enabled(type)) found.push(...FINDERS[name](text)); };
    run('email', 'email');
    run('iban', 'iban'); run('ccc', 'iban');
    run('tarjeta', 'tarjeta');
    run('dni', 'dni'); run('dniContext', 'dni');
    run('nie', 'nie'); run('nieContext', 'nie');
    run('cif', 'cif');
    run('pasaporte', 'pasaporte');
    run('nss', 'nss');
    run('telefono', 'telefono'); run('telefonoInt', 'telefono');
    run('ip', 'ip');
    run('matricula', 'matricula');
    run('cp', 'cp'); run('cpCiudad', 'cp');
    run('direccion', 'direccion');
    run('nacimiento', 'nacimiento');
    run('fecha', 'fecha');
    run('procedimiento', 'procedimiento');
    if (enabled('empresa')) found.push(...findCompanies(text));
    if (enabled('persona')) found.push(...findPersons(text));

    // Prioridad para resolver solapamientos (mayor = gana).
    const PRIO = { custom: 100, manual: 95, email: 90, iban: 85, tarjeta: 84, nss: 83, dni: 80, nie: 80, cif: 78, pasaporte: 77, nacimiento: 75, procedimiento: 72, ip: 70, telefono: 65, empresa: 60, direccion: 55, persona: 50, matricula: 45, cp: 40, fecha: 30 };
    found.sort((a, b) => a.start - b.start || (PRIO[b.type] - PRIO[a.type]) || (b.end - b.start) - (a.end - a.start));
    const chosen = [];
    for (const f of found) {
      const clash = chosen.find((c) => f.start < c.end && f.end > c.start);
      if (!clash) { chosen.push(f); continue; }
      const better = PRIO[f.type] > PRIO[clash.type] || (PRIO[f.type] === PRIO[clash.type] && f.end - f.start > clash.end - clash.start);
      if (better) chosen.splice(chosen.indexOf(clash), 1, f);
    }

    // Entidades únicas, en orden de aparición.
    const faker = new Faker(opt.style);
    const uniq = new Map();
    const addEntity = (type, txt, meta = {}, replacement) => {
      const t = txt.trim();
      if (!t) return null;
      const key = type + '|' + faker.keyFor(type, t);
      if (!uniq.has(key)) {
        const rep = replacement ?? faker.fake(type, t, meta);
        uniq.set(key, { id: 'e' + uniq.size, type, text: t, variants: new Set([t]), replacement: rep, enabled: true, meta });
      } else uniq.get(key).variants.add(t);
      return uniq.get(key);
    };
    // Términos personalizados primero (prioridad máxima).
    let ci = 0;
    for (const c of opt.custom) {
      if (!c.text.trim()) continue;
      ci++;
      addEntity('custom', c.text, {}, c.replacement || (opt.style === 'etiqueta' ? `[DATO ${ci}]` : `Dato Ficticio ${pick(GREEK, ci - 1)}`));
    }
    for (const e of opt.extraEntities || []) addEntity(e.type || 'manual', e.text, {}, e.replacement);
    for (const f of chosen.sort((a, b) => a.start - b.start)) addEntity(f.type, f.text, f.meta);

    // Partes sueltas de nombres de persona (apellidos o nombres que aparecen solos).
    if (enabled('persona')) {
      const persons = [...uniq.values()].filter((e) => e.type === 'persona');
      for (const p of persons) {
        const toks = p.text.split(/\s+/).filter((t) => !PARTICLES.has(norm(t)) && !/^[A-ZÁÉÍÓÚÑ]\.$/.test(t));
        if (toks.length < 2) continue;
        // Asociar cada palabra con su sustituto para mantener la coherencia.
        const fakeParts = opt.style === 'etiqueta' ? null : faker.personParts(p.text, p.meta);
        toks.forEach((t, i) => {
          if (t.length < 3 || STOP.has(norm(t))) return;
          const rep = fakeParts ? fakeParts[i] : p.replacement;
          const key = 'persona|' + faker.keyFor('persona', t);
          if (!uniq.has(key)) uniq.set(key, { id: 'e' + uniq.size, type: 'persona', text: t, variants: new Set([t]), replacement: rep, enabled: true, meta: { part: true } });
        });
      }
    }

    const list = [...uniq.values()];
    for (const e of list) e.count = countMatches(text, [e]);
    return list.filter((e) => e.count > 0 || e.type === 'custom' || e.type === 'manual');
  }

  // --------------------------------------------------- búsqueda y sustitución
  const ACC = { a: 'aáàäâ', e: 'eéèëê', i: 'iíìïî', o: 'oóòöô', u: 'uúùüû', n: 'nñ', c: 'cç' };
  function fuzzyPattern(s, ci) {
    let out = '';
    for (const ch of s) {
      const base = norm(ch);
      if (/\s/.test(ch)) { out += '\\s+'; continue; }
      if (ACC[base] && ci) { out += '[' + ACC[base] + ACC[base].toUpperCase() + ']'; continue; }
      if (ACC[base]) {
        const set = ch === ch.toUpperCase() ? ACC[base].toUpperCase() : ACC[base];
        out += '[' + set + ']';
        continue;
      }
      out += escRe(ch);
    }
    return out;
  }

  function entityPatterns(e) {
    // Devuelve [{re, ci}] para todas las variantes de la entidad.
    const pats = [];
    const textual = ['persona', 'empresa', 'direccion', 'manual', 'custom'].includes(e.type);
    for (const v of e.variants || [e.text]) {
      const multi = /\s/.test(v.trim());
      if (textual) {
        if (multi || e.type !== 'persona') pats.push({ src: fuzzyPattern(v, true), ci: true });
        else {
          pats.push({ src: fuzzyPattern(v, false), ci: false });
          pats.push({ src: fuzzyPattern(v.toUpperCase(), false), ci: false });
        }
      } else {
        // Identificadores: tolerar distinto formato (puntos, guiones, espacios).
        const core = v.replace(/[\s.\-\/]/g, '');
        if (core.length >= 5 && e.type !== 'email' && e.type !== 'ip') {
          pats.push({ src: core.split('').map(escRe).join('[\\s.\\-\\/]?'), ci: true });
        } else pats.push({ src: escRe(v), ci: true });
      }
    }
    return pats;
  }

  /** Encuentra coincidencias no solapadas de las entidades activas en un texto. */
  function findMatches(text, entities) {
    const all = [];
    for (const e of entities) {
      if (!e.enabled) continue;
      for (const p of entityPatterns(e)) {
        const v0 = (e.variants ? [...e.variants][0] : e.text) || '';
        const pre = /^[\p{L}\p{N}]/u.test(v0) ? `(?<![${L}0-9])` : '';
        const post = /[\p{L}\p{N}]$/u.test(v0) ? `(?![${L}0-9])` : '';
        const re = new RegExp(`${pre}(?:${p.src})${post}`, p.ci ? 'giu' : 'gu');
        let m;
        while ((m = re.exec(text))) {
          if (!m[0]) { re.lastIndex++; continue; }
          all.push({ start: m.index, end: m.index + m[0].length, entity: e, match: m[0] });
        }
      }
    }
    const prio = (e) => (e.type === 'custom' ? 3 : e.type === 'manual' ? 2 : 1);
    all.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start) || prio(b.entity) - prio(a.entity));
    const out = [];
    let lastEnd = -1;
    for (const m of all) {
      if (m.start >= lastEnd) { out.push(m); lastEnd = m.end; }
    }
    return out;
  }

  function countMatches(text, entities) { return findMatches(text, entities.map((e) => ({ ...e, enabled: true }))).length; }

  function adaptCase(match, replacement) {
    if (isUpperWord(match) && match.replace(/[^\p{L}]/gu, '').length > 1) return replacement.toUpperCase();
    return replacement;
  }

  function replaceText(text, entities) {
    const ms = findMatches(text, entities);
    let out = '', last = 0;
    for (const m of ms) {
      out += text.slice(last, m.start) + adaptCase(m.match, m.entity.replacement);
      last = m.end;
    }
    return out + text.slice(last);
  }

  global.Anonimizador = { FINDERS, entityPatterns, analyze, findMatches, replaceText, adaptCase, CATEGORIES, CAT_LABEL, validDni, validNie, Faker };
})(typeof window !== 'undefined' ? window : globalThis);
