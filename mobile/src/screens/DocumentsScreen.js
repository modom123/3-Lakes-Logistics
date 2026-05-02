import React, { useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Alert, ActivityIndicator, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as Haptics from 'expo-haptics';

import { useToast } from '../context';
import { colors, font, space, radius, shadow } from '../theme';

const DOC_TYPES = [
  {
    key:      'bol',
    label:    'Bill of Lading',
    short:    'BOL',
    icon:     'document-text',
    hint:     'Required — photograph or scan the BOL before departing.',
    required: true,
    color:    colors.primary,
    bg:       colors.primaryLight,
  },
  {
    key:      'pod',
    label:    'Proof of Delivery',
    short:    'POD',
    icon:     'checkmark-done',
    hint:     'Required — get receiver signature then upload.',
    required: true,
    color:    colors.success,
    bg:       colors.successLight,
  },
  {
    key:      'lumper',
    label:    'Lumper Receipt',
    short:    'Receipt',
    icon:     'receipt',
    hint:     'Optional — required only if lumper service was used.',
    required: false,
    color:    colors.warning,
    bg:       colors.warningLight,
  },
];

// ── Upload Card ───────────────────────────────────────────────────────────────

function UploadCard({ dt, uploaded, uploading, progress, onCamera, onFile, onRemove }) {
  return (
    <View style={[s.card, shadow.xs]}>
      {/* Header */}
      <View style={s.cardHeader}>
        <View style={[s.iconCircle, { backgroundColor: dt.bg }]}>
          <Ionicons name={dt.icon} size={20} color={dt.color} />
        </View>
        <View style={s.cardHeaderText}>
          <Text style={s.cardLabel}>{dt.label}</Text>
          <Text style={s.cardHint}>{dt.hint}</Text>
        </View>
        {dt.required && (
          <View style={s.reqBadge}>
            <Text style={s.reqText}>Required</Text>
          </View>
        )}
      </View>

      {/* State */}
      {uploading ? (
        <View style={s.uploadingRow}>
          <ActivityIndicator size="small" color={dt.color} />
          <View style={s.progressTrack}>
            <View style={[s.progressFill, { width: `${progress}%`, backgroundColor: dt.color }]} />
          </View>
          <Text style={[s.uploadingLabel, { color: dt.color }]}>{progress}%</Text>
        </View>
      ) : uploaded ? (
        <View style={[s.doneRow, { backgroundColor: dt.bg }]}>
          <Ionicons name="checkmark-circle" size={18} color={dt.color} />
          <Text style={[s.doneText, { color: dt.color }]}>{dt.short} uploaded successfully</Text>
          <TouchableOpacity onPress={onRemove} style={s.removeBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="refresh" size={15} color={dt.color} />
          </TouchableOpacity>
        </View>
      ) : (
        <View style={s.btnRow}>
          <TouchableOpacity style={[s.uploadBtn, { backgroundColor: dt.color }]} onPress={onCamera} activeOpacity={0.85}>
            <Ionicons name="camera" size={16} color={colors.white} />
            <Text style={s.uploadBtnText}>Camera</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.uploadBtn, s.uploadBtnOutline, { borderColor: dt.color }]} onPress={onFile} activeOpacity={0.85}>
            <Ionicons name="folder-open" size={16} color={dt.color} />
            <Text style={[s.uploadBtnText, { color: dt.color }]}>Choose File</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

// ── Uploaded doc row ──────────────────────────────────────────────────────────

function DocRow({ doc }) {
  const isImage = ['jpg','jpeg','png','heic','webp'].some(ext =>
    doc.name?.toLowerCase().endsWith(ext)
  );
  return (
    <View style={s.docRow}>
      <View style={[s.docIconWrap, { backgroundColor: colors.successLight }]}>
        <Ionicons name={isImage ? 'image' : 'document'} size={16} color={colors.success} />
      </View>
      <View style={s.docInfo}>
        <Text style={s.docType}>{doc.type}</Text>
        <Text style={s.docName} numberOfLines={1}>{doc.name}</Text>
      </View>
      <Text style={s.docTime}>{doc.time}</Text>
    </View>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function DocumentsScreen() {
  const { showToast } = useToast();
  const [uploaded,  setUploaded]  = useState({ bol: false, pod: false, lumper: false });
  const [uploading, setUploading] = useState({ bol: false, pod: false, lumper: false });
  const [progress,  setProgress]  = useState({ bol: 0,    pod: 0,    lumper: 0    });
  const [history,   setHistory]   = useState([]);

  async function reqCamera() {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Camera Permission', 'Enable camera access in Settings to photograph documents.');
      return false;
    }
    return true;
  }

  async function reqMedia() {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Photo Library', 'Enable photo library access in Settings to upload documents.');
      return false;
    }
    return true;
  }

  async function doUpload(key, label, asset) {
    setUploading(p => ({ ...p, [key]: true }));
    setProgress(p => ({ ...p, [key]: 0 }));

    // Simulated progress — replace with real FormData upload to your backend
    for (const pct of [20, 45, 70, 90, 100]) {
      await new Promise(r => setTimeout(r, 280));
      setProgress(p => ({ ...p, [key]: pct }));
    }

    const name = asset.fileName || asset.name || `${key}-${Date.now()}.jpg`;
    setUploaded(p  => ({ ...p,  [key]: true }));
    setUploading(p => ({ ...p,  [key]: false }));
    setHistory(h => [...h, { type: label, name, time: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) }]);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showToast(`${label} uploaded successfully.`, 'success');
  }

  async function handleCamera(key, label) {
    const ok = await reqCamera();
    if (!ok) return;
    const res = await ImagePicker.launchCameraAsync({ quality: 0.85, allowsEditing: false });
    if (res.canceled) return;
    doUpload(key, label, res.assets[0]);
  }

  async function handleFile(key, label) {
    let asset = null;
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'application/pdf'], copyToCacheDirectory: true });
      if (res.canceled) return;
      asset = res.assets?.[0];
    } catch {
      const ok = await reqMedia();
      if (!ok) return;
      const res = await ImagePicker.launchImageLibraryAsync({ quality: 0.85 });
      if (res.canceled) return;
      asset = res.assets?.[0];
    }
    if (asset) doUpload(key, label, asset);
  }

  const allDone   = uploaded.bol && uploaded.pod;
  const doneCount = Object.values(uploaded).filter(Boolean).length;

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.headerTitle}>Documents</Text>
          <Text style={s.headerSub}>{doneCount} of 3 uploaded this load</Text>
        </View>
        {allDone && (
          <View style={s.allDoneBadge}>
            <Ionicons name="checkmark-circle" size={14} color={colors.success} />
            <Text style={s.allDoneText}>Complete</Text>
          </View>
        )}
      </View>

      {/* Progress bar */}
      <View style={s.overallTrack}>
        <View style={[s.overallFill, { width: `${Math.round((doneCount / 3) * 100)}%` }]} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {DOC_TYPES.map(dt => (
          <UploadCard
            key={dt.key}
            dt={dt}
            uploaded={uploaded[dt.key]}
            uploading={uploading[dt.key]}
            progress={progress[dt.key]}
            onCamera={() => handleCamera(dt.key, dt.label)}
            onFile={()   => handleFile(dt.key,   dt.label)}
            onRemove={()  => setUploaded(p => ({ ...p, [dt.key]: false }))}
          />
        ))}

        {/* History */}
        <Text style={s.sectionTitle}>Uploaded This Load</Text>
        {history.length === 0 ? (
          <View style={[s.emptyHistory, shadow.xs]}>
            <Ionicons name="cloud-upload-outline" size={28} color={colors.border} />
            <Text style={s.emptyHistoryText}>No documents uploaded yet.</Text>
          </View>
        ) : (
          history.map((doc, i) => <DocRow key={i} doc={doc} />)
        )}

        <View style={{ height: space.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: colors.bg },
  header:{
    backgroundColor: colors.card, paddingHorizontal: space.base, paddingVertical: space.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  headerTitle:  { fontSize: font.lg, fontWeight: font.extrabold, color: colors.textPrimary },
  headerSub:    { fontSize: font.xs, color: colors.textSecondary, marginTop: 2 },
  allDoneBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.successLight, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.full },
  allDoneText:  { fontSize: font.xs, color: colors.success, fontWeight: font.bold },
  overallTrack: { height: 3, backgroundColor: colors.border },
  overallFill:  { height: '100%', backgroundColor: colors.success },
  scroll: { padding: space.base },
  sectionTitle: { fontSize: font.xs, fontWeight: font.bold, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginTop: space.base, marginBottom: space.sm },

  card: {
    backgroundColor: colors.card, borderRadius: radius.lg, padding: space.base,
    marginBottom: space.sm, borderWidth: 1, borderColor: colors.border,
  },
  cardHeader:     { flexDirection: 'row', alignItems: 'flex-start', marginBottom: space.md, gap: space.md },
  iconCircle:     { width: 40, height: 40, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  cardHeaderText: { flex: 1 },
  cardLabel:      { fontSize: font.base, fontWeight: font.bold, color: colors.textPrimary, marginBottom: 2 },
  cardHint:       { fontSize: font.xs, color: colors.textSecondary, lineHeight: 17 },
  reqBadge:       { backgroundColor: colors.dangerLight, borderRadius: radius.full, paddingHorizontal: 7, paddingVertical: 3, alignSelf: 'flex-start', flexShrink: 0 },
  reqText:        { fontSize: 10, fontWeight: font.bold, color: colors.danger },

  uploadingRow:  { flexDirection: 'row', alignItems: 'center', gap: space.sm, padding: space.sm, backgroundColor: colors.surface, borderRadius: radius.sm },
  progressTrack: { flex: 1, height: 4, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
  progressFill:  { height: '100%', borderRadius: 2 },
  uploadingLabel:{ fontSize: font.xs, fontWeight: font.bold, width: 30, textAlign: 'right' },

  doneRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, padding: space.md, borderRadius: radius.sm },
  doneText:{ flex: 1, fontSize: font.sm, fontWeight: font.semibold },
  removeBtn:{ padding: 4 },

  btnRow:       { flexDirection: 'row', gap: space.sm },
  uploadBtn:    { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.xs, borderRadius: radius.md, paddingVertical: 12 },
  uploadBtnOutline: { backgroundColor: 'transparent', borderWidth: 1.5 },
  uploadBtnText:{ fontSize: font.sm, fontWeight: font.bold, color: colors.white },

  docRow:     { flexDirection: 'row', alignItems: 'center', gap: space.md, backgroundColor: colors.card, borderRadius: radius.md, padding: space.md, marginBottom: space.sm, borderWidth: 1, borderColor: colors.border },
  docIconWrap:{ width: 34, height: 34, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  docInfo:    { flex: 1 },
  docType:    { fontSize: font.sm, fontWeight: font.bold, color: colors.textPrimary },
  docName:    { fontSize: font.xs, color: colors.textSecondary, marginTop: 1 },
  docTime:    { fontSize: font.xs, color: colors.textMuted },

  emptyHistory: { backgroundColor: colors.card, borderRadius: radius.md, padding: space.xl, alignItems: 'center', gap: space.sm, borderWidth: 1, borderColor: colors.border },
  emptyHistoryText: { fontSize: font.sm, color: colors.textMuted },
});
