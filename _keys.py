"""Claves hardcodeadas usadas para ofuscar datos en el código fuente.

Esto NO es cifrado seguro: la clave viaja con el código/ejecutable, así
que cualquiera que lo tenga puede recuperarla. Su único propósito es que
SERVER_URL y hashes.json no queden como texto plano a simple vista para
quien abra el .exe con un editor hexadecimal.
"""

OBFUSCATION_KEY = b"jwCOYGoQ4JvZulgnwBHeQSp1l_byF_PNL6vJzWjVDjI="
