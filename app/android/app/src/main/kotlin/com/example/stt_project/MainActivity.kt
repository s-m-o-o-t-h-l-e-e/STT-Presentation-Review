package com.example.stt_project

import android.app.Activity
import android.content.Intent
import android.net.Uri
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.android.FlutterActivity
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream

class MainActivity : FlutterActivity() {
    private val reportChannel = "stt_project/report_saver"
    private val createReportRequestCode = 4207
    private var pendingReportPath: String? = null
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, reportChannel)
            .setMethodCallHandler { call, result ->
                if (call.method != "savePdf") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }

                val filePath = call.argument<String>("filePath")
                val fileName = call.argument<String>("fileName") ?: "presentation-review-report.pdf"
                if (filePath.isNullOrBlank()) {
                    result.error("missing_file", "PDF file path is missing.", null)
                    return@setMethodCallHandler
                }
                if (pendingResult != null) {
                    result.error("save_in_progress", "Another PDF save request is already open.", null)
                    return@setMethodCallHandler
                }

                pendingReportPath = filePath
                pendingResult = result
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                    putExtra(Intent.EXTRA_TITLE, fileName)
                }
                startActivityForResult(intent, createReportRequestCode)
            }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != createReportRequestCode) return

        val result = pendingResult
        val sourcePath = pendingReportPath
        pendingResult = null
        pendingReportPath = null

        if (resultCode != Activity.RESULT_OK || data?.data == null) {
            result?.success(null)
            return
        }
        if (sourcePath.isNullOrBlank()) {
            result?.error("missing_file", "PDF file path is missing.", null)
            return
        }

        try {
            val targetUri: Uri = data.data!!
            contentResolver.openOutputStream(targetUri)?.use { output ->
                FileInputStream(File(sourcePath)).use { input ->
                    input.copyTo(output)
                }
            } ?: throw IllegalStateException("Cannot open selected file.")
            result?.success(targetUri.toString())
        } catch (error: Exception) {
            result?.error("save_failed", error.message, null)
        }
    }
}
