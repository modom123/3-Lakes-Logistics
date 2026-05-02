import React, { useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { colors, typography, spacing, radius } from '../theme';

const DOC_TYPES = [
  {
    key: 'bol',
    label: 'Bill of Lading (BOL)',
    icon: '📄',
    hint: 'Take a photo or choose PDF',
    required: true,
  },
  {
    key: 'pod',
    label: 'Proof of Delivery (POD)',
    icon: '✍️',
    hint: 'Get receiver signature then upload',
    required: true,
  },
  {
    key: 'lumper',
    label: 'Lumper Receipt',
    icon: '🧾',
    hint: 'Required for reimbursement',
    required: false,
  },
];

function UploadCard({ docType, uploaded, uploading, onCamera, onFile }) {
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <Text style={s.cardTitle}>{docType.label}</Text>
        {docType.required && <Text style={s.required}>Required</Text>}
      </View>

      {uploaded ? (
        <View style={s.uploadedRow}>
          <Text style={s.uploadedIcon}>✅</Text>
          <Text style={s.uploadedText}>{docType.label} uploaded successfully</Text>
        </View>
      ) : uploading ? (
        <View style={s.uploadingRow}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={s.uploadingText}>Uploading…</Text>
        </View>
      ) : (
        <>
          <Text style={s.hint}>{docType.hint}</Text>
          <View style={s.btnRow}>
            <TouchableOpacity style={s.uploadBtn} onPress={onCamera} activeOpacity={0.8}>
              <Text style={s.uploadBtnIcon}>📷</Text>
              <Text style={s.uploadBtnText}>Take Photo</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.uploadBtn, s.uploadBtnSecondary]} onPress={onFile} activeOpacity={0.8}>
              <Text style={s.uploadBtnIcon}>📁</Text>
              <Text style={[s.uploadBtnText, { color: colors.primary }]}>Choose File</Text>
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );
}

export default function DocumentsScreen() {
  const [uploaded, setUploaded] = useState({ bol: false, pod: false, lumper: false });
  const [uploading, setUploading] = useState({ bol: false, pod: false, lumper: false });
  const [uploadedDocs, setUploadedDocs] = useState([]);

  useFocusEffect(
    useCallback(() => {
      // Reset on each focus so driver can upload fresh docs per load
    }, [])
  );

  async function requestCameraPermission() {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert(
        'Camera Permission Required',
        'Please enable camera access in your device settings to take photos.',
      );
      return false;
    }
    return true;
  }

  async function requestMediaPermission() {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert(
        'Photo Library Permission Required',
        'Please enable photo library access in your device settings.',
      );
      return false;
    }
    return true;
  }

  async function handleCamera(key, label) {
    const ok = await requestCameraPermission();
    if (!ok) return;

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
      allowsEditing: false,
    });

    if (result.canceled) return;
    await uploadFile(key, label, result.assets[0]);
  }

  async function handleFilePicker(key, label) {
    let result;
    try {
      result = await DocumentPicker.getDocumentAsync({
        type: ['image/*', 'application/pdf'],
        copyToCacheDirectory: true,
      });
    } catch {
      // Try image picker as fallback
      const mediaOk = await requestMediaPermission();
      if (!mediaOk) return;
      const imgResult = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.85,
      });
      if (imgResult.canceled) return;
      await uploadFile(key, label, imgResult.assets[0]);
      return;
    }

    if (result.canceled) return;
    const asset = result.assets?.[0];
    if (!asset) return;
    await uploadFile(key, label, asset);
  }

  async function uploadFile(key, label, asset) {
    setUploading(prev => ({ ...prev, [key]: true }));
    try {
      // Simulate upload — in production, use FormData with fetch to your backend
      await new Promise(resolve => setTimeout(resolve, 1500));

      setUploaded(prev => ({ ...prev, [key]: true }));
      const name = asset.fileName || asset.name || `${key}-${Date.now()}.jpg`;
      setUploadedDocs(prev => [
        ...prev,
        {
          type: label,
          name,
          ts: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }),
        },
      ]);
    } catch {
      Alert.alert('Upload Failed', 'Could not upload the document. Check your connection and try again.');
    } finally {
      setUploading(prev => ({ ...prev, [key]: false }));
    }
  }

  const allRequired = uploaded.bol && uploaded.pod;

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Documents</Text>
        {allRequired && <Text style={s.allGood}>✓ All required docs uploaded</Text>}
      </View>

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Text style={s.sectionTitle}>Upload Documents</Text>

        {DOC_TYPES.map(dt => (
          <UploadCard
            key={dt.key}
            docType={dt}
            uploaded={uploaded[dt.key]}
            uploading={uploading[dt.key]}
            onCamera={() => handleCamera(dt.key, dt.label)}
            onFile={() => handleFilePicker(dt.key, dt.label)}
          />
        ))}

        {/* Uploaded list */}
        <Text style={s.sectionTitle}>Uploaded This Load</Text>
        {uploadedDocs.length === 0 ? (
          <View style={s.noDocsWrap}>
            <Text style={s.noDocs}>No documents uploaded yet for this load.</Text>
          </View>
        ) : (
          uploadedDocs.map((doc, i) => (
            <View key={i} style={s.docRow}>
              <Text style={s.docIcon}>✅</Text>
              <View style={s.docInfo}>
                <Text style={s.docType}>{doc.type}</Text>
                <Text style={s.docName} numberOfLines={1}>{doc.name}</Text>
              </View>
              <Text style={s.docTime}>{doc.ts}</Text>
            </View>
          ))
        )}

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    backgroundColor: colors.white,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: { fontSize: typography.lg, fontWeight: '800', color: colors.textPrimary },
  allGood: { fontSize: typography.xs, color: colors.success, fontWeight: '700' },
  scroll: { padding: spacing.md },
  sectionTitle: {
    fontSize: typography.xs,
    fontWeight: '700',
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  card: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.lg,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
  cardTitle: { fontSize: typography.base, fontWeight: '700', color: colors.textPrimary },
  required: {
    fontSize: typography.xs,
    color: colors.error,
    fontWeight: '700',
    backgroundColor: colors.errorLight,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.full,
  },
  hint: { fontSize: typography.sm, color: colors.textSecondary, marginBottom: spacing.md },
  btnRow: { flexDirection: 'row', gap: spacing.sm },
  uploadBtn: {
    flex: 1,
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    paddingVertical: 12,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  uploadBtnSecondary: {
    backgroundColor: colors.primaryLight,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  uploadBtnIcon: { fontSize: 16 },
  uploadBtnText: { fontSize: typography.sm, fontWeight: '700', color: colors.white },
  uploadedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.successLight,
    borderRadius: radius.sm,
    padding: spacing.md,
  },
  uploadedIcon: { fontSize: 18 },
  uploadedText: { fontSize: typography.sm, color: colors.success, fontWeight: '600' },
  uploadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
  },
  uploadingText: { fontSize: typography.sm, color: colors.textSecondary },
  noDocsWrap: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  noDocs: { fontSize: typography.sm, color: colors.textSecondary, textAlign: 'center' },
  docRow: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
  },
  docIcon: { fontSize: 20 },
  docInfo: { flex: 1 },
  docType: { fontSize: typography.sm, fontWeight: '700', color: colors.textPrimary },
  docName: { fontSize: typography.xs, color: colors.textSecondary, marginTop: 2 },
  docTime: { fontSize: typography.xs, color: colors.textMuted },
});
