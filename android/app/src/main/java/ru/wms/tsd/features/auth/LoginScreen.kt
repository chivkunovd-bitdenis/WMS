package ru.wms.tsd.features.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import ru.wms.tsd.core.auth.AuthManager
import ru.wms.tsd.core.auth.AuthStore
import ru.wms.tsd.core.auth.toLoginErrorMessage
import ru.wms.tsd.core.api.NetworkFailure
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * Ряд из 4 точек-индикаторов для отображения количества введённых цифр PIN.
 * Заполненная точка для каждой цифры, пустая контур для остальных.
 */
@Composable
private fun PinDots(count: Int) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        modifier = Modifier.padding(vertical = 16.dp),
    ) {
        repeat(4) { index ->
            Box(
                modifier = Modifier
                    .width(20.dp)
                    .height(20.dp)
                    .then(
                        if (index < count) {
                            Modifier.background(WmsColors.Primary, CircleShape)
                        } else {
                            Modifier.border(2.dp, WmsColors.TextSecondary, CircleShape)
                        }
                    ),
            )
        }
    }
}

/**
 * Экран A1. Логин — два состояния:
 * 1. Если есть сохранённые сотрудники → плитки с PIN-вводом;
 * 2. Иначе → форма email+пароль с опциональным полем адреса сервера.
 */
@Composable
fun LoginScreen(
    authStore: AuthStore,
    authManager: AuthManager,
    onLoginSuccess: () -> Unit,
) {
    val coroutineScope = rememberCoroutineScope()
    val savedStaff = remember { authStore.getSavedStaff() }
    var showPinDialog by remember { mutableStateOf(false) }
    var selectedEmail by remember { mutableStateOf("") }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = WmsColors.Background,
    ) {
        if (savedStaff.isNotEmpty() && !showPinDialog) {
            StaffSelectionScreen(
                staff = savedStaff,
                onStaffSelected = { email ->
                    selectedEmail = email
                    showPinDialog = true
                },
                onLoginWithPassword = {
                    showPinDialog = false
                },
                authStore = authStore,
                authManager = authManager,
                onLoginSuccess = onLoginSuccess,
            )
        } else if (showPinDialog) {
            PinLoginDialog(
                email = selectedEmail,
                authManager = authManager,
                onSuccess = onLoginSuccess,
                onBack = { showPinDialog = false },
            )
        } else {
            EmailPasswordLoginScreen(
                authStore = authStore,
                authManager = authManager,
                onLoginSuccess = onLoginSuccess,
            )
        }
    }
}

/**
 * Экран выбора сотрудника из сохранённых + PIN.
 */
@Composable
private fun StaffSelectionScreen(
    staff: List<ru.wms.tsd.core.auth.SavedStaff>,
    onStaffSelected: (String) -> Unit,
    onLoginWithPassword: () -> Unit,
    authStore: AuthStore,
    authManager: AuthManager,
    onLoginSuccess: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            "Кто работает?",
            fontSize = 24.sp,
            modifier = Modifier
                .align(Alignment.CenterHorizontally)
                .padding(vertical = 16.dp),
        )

        LazyVerticalGrid(
            columns = GridCells.Fixed(1),
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(staff.size) { index ->
                val s = staff[index]
                Button(
                    onClick = { onStaffSelected(s.email) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(WmsDimens.TouchTargetMin),
                    colors = ButtonDefaults.buttonColors(containerColor = WmsColors.Primary),
                ) {
                    Text(s.displayName, fontSize = 20.sp)
                }
            }
        }

        TextButton(
            onClick = onLoginWithPassword,
            modifier = Modifier
                .align(Alignment.CenterHorizontally)
                .padding(bottom = 16.dp),
        ) {
            Text("Войти по паролю", fontSize = 16.sp, color = WmsColors.Primary)
        }
    }
}

/**
 * Диалог ввода PIN для выбранного сотрудника.
 */
@Composable
private fun PinLoginDialog(
    email: String,
    authManager: AuthManager,
    onSuccess: () -> Unit,
    onBack: () -> Unit,
) {
    var pinInput by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }
    val coroutineScope = rememberCoroutineScope()

    fun submitPin() {
        if (pinInput.length != 4) {
            errorMessage = "Введите 4 цифры"
            return
        }
        val result = authManager.loginWithPin(email, pinInput)
        if (result.isSuccess) {
            onSuccess()
        } else {
            errorMessage = "Неверный PIN"
            pinInput = ""
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "Введите PIN",
            fontSize = 20.sp,
        )

        PinDots(pinInput.length)

        if (errorMessage.isNotEmpty()) {
            Text(
                errorMessage,
                fontSize = 16.sp,
                color = WmsColors.Error,
                textAlign = TextAlign.Center,
            )
        }

        // Цифровая клавиатура 3x4
        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(12) { index ->
                val digit = when (index) {
                    0 -> "1"
                    1 -> "2"
                    2 -> "3"
                    3 -> "4"
                    4 -> "5"
                    5 -> "6"
                    6 -> "7"
                    7 -> "8"
                    8 -> "9"
                    9 -> "0"
                    10 -> "←"
                    11 -> "✓"
                    else -> ""
                }

                Button(
                    onClick = {
                        when (digit) {
                            "←" -> pinInput = pinInput.dropLast(1)
                            "✓" -> submitPin()
                            else -> {
                                if (pinInput.length < 4) pinInput += digit
                                errorMessage = ""
                            }
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(WmsDimens.TouchTargetMin),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (digit == "✓") WmsColors.Success else WmsColors.Primary,
                    ),
                ) {
                    Text(digit, fontSize = 20.sp)
                }
            }
        }

        TextButton(
            onClick = onBack,
            modifier = Modifier.padding(top = 16.dp),
        ) {
            Text("Назад", color = WmsColors.Primary)
        }
    }
}

/**
 * Форма email+пароль с опциональным полем адреса сервера.
 */
@Composable
private fun EmailPasswordLoginScreen(
    authStore: AuthStore,
    authManager: AuthManager,
    onLoginSuccess: () -> Unit,
) {
    val coroutineScope = rememberCoroutineScope()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var baseUrl by remember { mutableStateOf(authManager.getWorkingBaseUrl()) }
    var showServerSettings by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var isCheckingConnection by remember { mutableStateOf(false) }
    var connectionCheckSucceeded by remember { mutableStateOf<Boolean?>(null) }
    var connectionStatusMessage by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }
    var showPinSetup by remember { mutableStateOf(false) }
    var pin1 by remember { mutableStateOf("") }
    var pin2 by remember { mutableStateOf("") }

    fun submitLogin() {
        if (email.isBlank() || password.isBlank()) {
            errorMessage = "Заполните все поля"
            return
        }
        isLoading = true
        errorMessage = ""
        coroutineScope.launch {
            val result = authManager.loginWithPassword(baseUrl, email, password)
            isLoading = false
            if (result.isSuccess) {
                showPinSetup = true
            } else {
                errorMessage = result.exceptionOrNull()?.toLoginErrorMessage()
                    ?: NetworkFailure.Unknown.toOperatorMessage()
            }
        }
    }
    fun checkConnection() {
        isCheckingConnection = true
        connectionCheckSucceeded = null
        connectionStatusMessage = ""
        errorMessage = ""
        coroutineScope.launch {
            val result = authManager.checkServerConnection(baseUrl)
            isCheckingConnection = false
            if (result.isSuccess) {
                connectionCheckSucceeded = true
                connectionStatusMessage = "Соединение установлено"
            } else {
                connectionCheckSucceeded = false
                connectionStatusMessage = result.exceptionOrNull()?.toLoginErrorMessage()
                    ?: NetworkFailure.Unknown.toOperatorMessage()
            }
        }
    }

    fun restoreWorkingBaseUrl() {
        baseUrl = authManager.getWorkingBaseUrl()
        connectionCheckSucceeded = null
        connectionStatusMessage = ""
        errorMessage = ""
    }

    fun submitPinSetup(pin1: String, pin2: String) {
        if (pin1.length != 4 || pin2.length != 4) {
            errorMessage = "Введите 4-значный PIN дважды"
            return
        }
        if (pin1 != pin2) {
            errorMessage = "PINы не совпадают"
            return
        }
        val session = authManager.getCurrentSession()
        if (session != null) {
            authStore.saveStaff(
                ru.wms.tsd.core.auth.SavedStaff(
                    email = session.email,
                    displayName = session.displayName,
                    token = session.token,
                    pin = pin1,
                )
            )
        }
        onLoginSuccess()
    }

    AnimatedContent(targetState = showPinSetup) { isPinSetup ->
        if (!isPinSetup) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("Вход", fontSize = 24.sp, modifier = Modifier.padding(top = 16.dp))

                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    enabled = !isLoading,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Email,
                        imeAction = ImeAction.Next,
                    ),
                )

                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Пароль") },
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    enabled = !isLoading,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(onDone = { submitLogin() }),
                )

                // Свёрнутое поле адреса сервера
                if (!showServerSettings) {
                    TextButton(
                        onClick = { showServerSettings = true },
                        modifier = Modifier.align(Alignment.Start),
                    ) {
                        Text("Настройки сервера", fontSize = 14.sp, color = WmsColors.Primary)
                    }
                } else {
                    OutlinedTextField(
                        value = baseUrl,
                        onValueChange = {
                            baseUrl = it
                            connectionCheckSucceeded = null
                            connectionStatusMessage = ""
                        },
                        label = { Text("Адрес сервера") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        enabled = !isLoading && !isCheckingConnection,
                    )
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        TextButton(
                            onClick = { checkConnection() },
                            enabled = !isLoading && !isCheckingConnection,
                            modifier = Modifier.align(Alignment.Start),
                        ) {
                            if (isCheckingConnection) {
                                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                            }
                            Text("Проверить соединение", fontSize = 14.sp, color = WmsColors.Primary)
                        }
                        TextButton(
                            onClick = { restoreWorkingBaseUrl() },
                            enabled = !isLoading && !isCheckingConnection,
                            modifier = Modifier.align(Alignment.Start),
                        ) {
                            Text("Вернуть рабочий адрес", fontSize = 14.sp, color = WmsColors.Primary)
                        }
                    }
                    if (connectionStatusMessage.isNotEmpty()) {
                        Text(
                            connectionStatusMessage,
                            fontSize = 14.sp,
                            color = when (connectionCheckSucceeded) {
                                true -> WmsColors.Success
                                false -> WmsColors.Error
                                null -> WmsColors.TextSecondary
                            },
                            textAlign = TextAlign.Start,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    TextButton(
                        onClick = { showServerSettings = false },
                        modifier = Modifier.align(Alignment.Start),
                    ) {
                        Text("Свернуть", fontSize = 14.sp, color = WmsColors.Primary)
                    }
                }

                if (errorMessage.isNotEmpty()) {
                    Text(
                        errorMessage,
                        fontSize = 16.sp,
                        color = WmsColors.Error,
                        textAlign = TextAlign.Center,
                    )
                }

                Box(modifier = Modifier.weight(1f))

                Button(
                    onClick = { submitLogin() },
                    enabled = !isLoading && email.isNotBlank() && password.isNotBlank(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(WmsDimens.PrimaryButtonHeight),
                ) {
                    if (isLoading) {
                        CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                    }
                    Text("Войти", fontSize = 20.sp)
                }
            }
        } else {
            PinSetupDialog(
                onComplete = { p1, p2 -> submitPinSetup(p1, p2) },
                onError = { msg -> errorMessage = msg },
                errorMessage = errorMessage,
            )
        }
    }
}

/**
 * Диалог установки PIN после успешного входа по паролю.
 */
@Composable
private fun PinSetupDialog(
    onComplete: (pin1: String, pin2: String) -> Unit,
    onError: (String) -> Unit,
    errorMessage: String,
) {
    var pin1 by remember { mutableStateOf("") }
    var pin2 by remember { mutableStateOf("") }
    var step by remember { mutableStateOf(1) } // 1 = ввод PIN, 2 = подтверждение

    fun handleDigit(digit: String) {
        if (step == 1) {
            when (digit) {
                "←" -> pin1 = pin1.dropLast(1)
                "✓" -> {
                    if (pin1.length == 4) {
                        step = 2
                    } else {
                        onError("Введите 4 цифры")
                    }
                }
                else -> if (pin1.length < 4) pin1 += digit
            }
        } else {
            when (digit) {
                "←" -> pin2 = pin2.dropLast(1)
                "✓" -> {
                    if (pin2.length == 4) {
                        onComplete(pin1, pin2)
                    } else {
                        onError("Введите 4 цифры")
                    }
                }
                else -> if (pin2.length < 4) pin2 += digit
            }
        }
    }

    val currentPin = if (step == 1) pin1 else pin2

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            if (step == 1) "Установите PIN (4 цифры)" else "Повторите PIN",
            fontSize = 20.sp,
        )

        PinDots(currentPin.length)

        if (errorMessage.isNotEmpty()) {
            Text(
                errorMessage,
                fontSize = 16.sp,
                color = WmsColors.Error,
                textAlign = TextAlign.Center,
            )
        }

        // Цифровая клавиатура 3x4
        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(12) { index ->
                val digit = when (index) {
                    0 -> "1"
                    1 -> "2"
                    2 -> "3"
                    3 -> "4"
                    4 -> "5"
                    5 -> "6"
                    6 -> "7"
                    7 -> "8"
                    8 -> "9"
                    9 -> "0"
                    10 -> "←"
                    11 -> "✓"
                    else -> ""
                }

                Button(
                    onClick = { handleDigit(digit) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(WmsDimens.TouchTargetMin),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (digit == "✓") WmsColors.Success else WmsColors.Primary,
                    ),
                ) {
                    Text(digit, fontSize = 20.sp)
                }
            }
        }
    }
}
